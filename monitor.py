"""
Tournament monitor — polls the configured Lichess broadcast and posts to Discord.

Flow:
1. Every ROUND_CHECK_INTERVAL_SECONDS: fetch rounds for MONITORED_BROADCAST_ID
2. Reminders and round-start posts go to the chess channel (no per-user follow list)
3. Poll active round PGN every POLL_INTERVAL_SECONDS; classify moves; post alerts
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord

from chess_engine import (
    classify_move,
    format_eval,
    get_winning_side,
    is_alert_worthy,
    parse_cloud_eval,
    evaluate_with_chess_api,
)
from embeds import (
    build_game_over_embed,
    build_move_embed,
    build_reminder_embed,
    build_round_start_embed,
)
from groq_commentary import (
    generate_move_commentary,
    generate_reminder_message,
    generate_round_start_message,
)
from lichess_client import LichessClient
from pgn_parser import (
    get_game_id,
    get_last_move_san,
    get_latest_fen,
    get_move_count,
    is_game_over,
    parse_pgn_games,
)
import settings

logger = logging.getLogger("maggie-man.monitor")


@dataclass
class GameState:
    game_id: str
    white: str
    black: str
    move_count: int = 0
    last_fen: str = ""
    last_eval: float | None = None
    last_mate: int | None = None
    is_over: bool = False
    board_number: int | None = None


@dataclass
class RoundState:
    round_id: str
    round_name: str
    started: bool = False
    reminder_sent: bool = False
    start_announced: bool = False
    start_time: datetime | None = None
    games: dict = field(default_factory=dict)
    finished_game_ids: set = field(default_factory=set)


class TournamentMonitor:
    def __init__(
        self,
        bot: discord.Client,
        channel_id: int,
        groq_api_key: str,
        lichess_client: LichessClient | None = None,
    ):
        self.bot = bot
        self.channel_id = channel_id
        self.groq_api_key = groq_api_key
        self.broadcast_id = settings.MONITORED_BROADCAST_ID
        self.broadcast_url = settings.MONITORED_BROADCAST_URL
        self.lichess = lichess_client or LichessClient(
            api_base=settings.LICHESS_API_BASE,
            cloud_eval_url=settings.LICHESS_CLOUD_EVAL_URL,
            site_base=settings.LICHESS_SITE_BASE,
            oauth_token=settings.LICHESS_API_TOKEN,
        )

        self.rounds: dict[str, RoundState] = {}
        self.active_round_id: str | None = None
        self._running = False
        self._moves_analysed = 0

        self._poll_task: asyncio.Task | None = None
        self._round_check_task: asyncio.Task | None = None

    def start(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        self._round_check_task = loop.create_task(self._round_check_loop())
        self._poll_task = loop.create_task(self._poll_loop())
        logger.info("Monitor tasks started (round check + game poll)")

    def stop(self) -> None:
        self._running = False
        for t in (self._poll_task, self._round_check_task):
            if t:
                t.cancel()

    def get_status(self) -> dict:
        active_games = 0
        if self.active_round_id and self.active_round_id in self.rounds:
            active_games = len(self.rounds[self.active_round_id].games)
        return {
            "running": self._running,
            "active_games": active_games,
            "rounds_tracked": len(self.rounds),
            "moves_analysed": self._moves_analysed,
            "active_round": self.active_round_id,
            "broadcast_id": self.broadcast_id,
        }

    async def _round_check_loop(self) -> None:
        await asyncio.sleep(3)
        while self._running:
            try:
                await self._check_rounds()
            except Exception as e:
                logger.error("Round check error: %s", e, exc_info=True)
            await asyncio.sleep(settings.ROUND_CHECK_INTERVAL_SECONDS)

    async def _check_rounds(self) -> None:
        rounds = await self.lichess.get_broadcast_rounds(self.broadcast_id)
        if not rounds:
            logger.warning("_check_rounds: empty rounds for broadcast %s", self.broadcast_id)
            return

        now = datetime.now(timezone.utc)

        for r in rounds:
            round_info = r
            round_id = round_info.get("id")
            if not round_id:
                continue

            round_name = round_info.get("name", f"Round {round_id}")
            started = round_info.get("ongoing", False) or round_info.get("started", False)
            finished = round_info.get("finished", False)
            start_ts = round_info.get("startsAt")

            start_time = None
            if start_ts:
                try:
                    start_time = datetime.fromtimestamp(int(start_ts) / 1000, tz=timezone.utc)
                except Exception as e:
                    logger.warning("Could not parse startsAt=%s: %s", start_ts, e)

            if round_id not in self.rounds:
                logger.info(
                    "Discovered round: %s (id=%s, started=%s, finished=%s)",
                    round_name,
                    round_id,
                    started,
                    finished,
                )
                self.rounds[round_id] = RoundState(
                    round_id=round_id,
                    round_name=round_name,
                    start_time=start_time,
                )

            state = self.rounds[round_id]
            state.start_time = start_time

            if (
                not state.reminder_sent
                and not started
                and not finished
                and start_time
            ):
                secs_until = (start_time - now).total_seconds()
                if 0 < secs_until <= settings.REMINDER_MINUTES_BEFORE * 60:
                    state.reminder_sent = True
                    mins = int(secs_until // 60)
                    logger.info("Sending reminder for %s (%s min away)", round_name, mins)
                    await self._send_reminder(round_name, mins)

            if started and not finished and not state.start_announced:
                state.started = True
                state.start_announced = True
                self.active_round_id = round_id
                logger.info("Round started: %s (id=%s)", round_name, round_id)

                pgn = await self.lichess.get_round_pgn(round_id)
                pairings = []
                if pgn:
                    games = parse_pgn_games(pgn)
                    for i, g in enumerate(games):
                        try:
                            board = int(g["headers"].get("Board", i + 1))
                        except (ValueError, TypeError):
                            board = i + 1
                        pairings.append(
                            {
                                "white": g["white"],
                                "black": g["black"],
                                "board": board,
                            }
                        )
                await self._send_round_start(round_name, pairings)

            if started and not finished:
                self.active_round_id = round_id

    async def _poll_loop(self) -> None:
        await asyncio.sleep(5)
        while self._running:
            try:
                if self.active_round_id:
                    await self._poll_active_round()
                else:
                    logger.debug("_poll_loop: no active round yet")
            except Exception as e:
                logger.error("Poll loop error: %s", e, exc_info=True)
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def _poll_active_round(self) -> None:
        round_id = self.active_round_id
        pgn = await self.lichess.get_round_pgn(round_id)
        if not pgn:
            return

        games = parse_pgn_games(pgn)
        if not games:
            return

        round_state = self.rounds.get(round_id)
        if not round_state:
            round_state = RoundState(round_id=round_id, round_name=f"Round {round_id}")
            self.rounds[round_id] = round_state

        round_name = round_state.round_name

        for i, game in enumerate(games):
            game_id = get_game_id(game)

            try:
                board_num = int(game["headers"].get("Board", i + 1))
            except (ValueError, TypeError):
                board_num = i + 1

            if game_id not in round_state.games:
                round_state.games[game_id] = GameState(
                    game_id=game_id,
                    white=game["white"],
                    black=game["black"],
                    board_number=board_num,
                )
                logger.info(
                    "Tracking new game: Board %s %s vs %s",
                    board_num,
                    game["white"],
                    game["black"],
                )

            gs = round_state.games[game_id]

            if gs.is_over:
                continue

            if is_game_over(game) and game_id not in round_state.finished_game_ids:
                gs.is_over = True
                round_state.finished_game_ids.add(game_id)
                await self._send_game_over(game, gs, round_name)
                continue

            current_move_count = get_move_count(game)
            if current_move_count <= gs.move_count:
                continue

            gs.move_count = current_move_count
            latest_fen = get_latest_fen(game)
            last_move_san = get_last_move_san(game)

            if not latest_fen or not last_move_san:
                continue

            turn_before = "w" if (current_move_count % 2 == 1) else "b"
            move_number = (current_move_count + 1) // 2

            logger.info(
                "[%s] Board %s %s vs %s | move %s: %s (ply %s)",
                round_name,
                board_num,
                game["white"],
                game["black"],
                move_number,
                last_move_san,
                current_move_count,
            )

            eval_after, mate_after, best_move, continuation = await self._evaluate(latest_fen)
            self._moves_analysed += 1

            classification = classify_move(gs.last_eval, eval_after, turn_before)

            logger.info(
                "  → eval: %s → %s | %s",
                format_eval(gs.last_eval, gs.last_mate),
                format_eval(eval_after, mate_after),
                classification,
            )

            if is_alert_worthy(classification):
                await self._send_move_alert(
                    game=game,
                    gs=gs,
                    round_name=round_name,
                    move_san=last_move_san,
                    move_number=move_number,
                    classification=classification,
                    eval_before=gs.last_eval,
                    eval_after=eval_after,
                    mate_before=gs.last_mate,
                    mate_after=mate_after,
                    best_move=best_move,
                    continuation=continuation,
                )

            gs.last_fen = latest_fen
            gs.last_eval = eval_after
            gs.last_mate = mate_after

    async def _evaluate(self, fen: str) -> tuple:
        cloud = await self.lichess.cloud_eval(fen, multi_pv=3)
        if cloud:
            ev, mate, best, cont = parse_cloud_eval(cloud)
            return ev, mate, best, cont

        logger.debug("Cloud eval miss — chess-api.com fallback")
        return await evaluate_with_chess_api(fen)

    async def _get_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error("Cannot get channel %s: %s", self.channel_id, e)
                return None
        return channel

    async def _send_reminder(self, round_name: str, minutes: int) -> None:
        channel = await self._get_channel()
        if not channel:
            return
        commentary = await generate_reminder_message(
            round_name, minutes, self.groq_api_key, settings.GROQ_MODEL
        )
        embed = build_reminder_embed(
            round_name, minutes, commentary, self.broadcast_url
        )
        await channel.send(embed=embed)

    async def _send_round_start(self, round_name: str, pairings: list[dict]) -> None:
        channel = await self._get_channel()
        if not channel:
            return
        commentary = await generate_round_start_message(
            round_name, pairings, self.groq_api_key, settings.GROQ_MODEL
        )
        embed = build_round_start_embed(
            round_name, pairings, commentary, self.broadcast_url
        )
        await channel.send(embed=embed)

    async def _send_move_alert(
        self,
        game,
        gs,
        round_name,
        move_san,
        move_number,
        classification,
        eval_before,
        eval_after,
        mate_before,
        mate_after,
        best_move,
        continuation,
    ) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        winning_side = get_winning_side(eval_after, mate_after)
        commentary = await generate_move_commentary(
            white=game["white"],
            black=game["black"],
            round_name=round_name,
            move_san=move_san,
            classification=classification,
            eval_before=eval_before if eval_before is not None else 0.0,
            eval_after=eval_after if eval_after is not None else 0.0,
            top_move=best_move,
            continuation=continuation,
            winning_side=winning_side,
            board_number=gs.board_number,
            groq_api_key=self.groq_api_key,
            model=settings.GROQ_MODEL,
        )

        embed = build_move_embed(
            white=game["white"],
            black=game["black"],
            round_name=round_name,
            board_number=gs.board_number,
            move_san=move_san,
            move_number=move_number,
            classification=classification,
            eval_before=eval_before if eval_before is not None else 0.0,
            eval_after=eval_after if eval_after is not None else 0.0,
            mate_before=mate_before,
            mate_after=mate_after,
            top_move=best_move,
            continuation=continuation,
            commentary=commentary,
            lichess_url=game.get("site", self.broadcast_url),
        )

        await channel.send(embed=embed)

    async def _send_game_over(self, game: dict, gs: GameState, round_name: str) -> None:
        channel = await self._get_channel()
        if not channel:
            return
        embed = build_game_over_embed(
            white=game["white"],
            black=game["black"],
            result=game["result"],
            round_name=round_name,
            board_number=gs.board_number,
            total_moves=gs.move_count,
        )
        await channel.send(embed=embed)
