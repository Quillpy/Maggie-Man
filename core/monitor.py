from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord

from api.lichess import LichessClient
from utils.engine import classify_move, evaluate_with_chess_api, format_eval, get_winning_side, is_alert_worthy, parse_cloud_eval
from utils.embeds import build_move_embed, build_reminder_embed
from utils.groq import generate_move_commentary, generate_reminder_message
from utils.pgn import get_game_id, get_last_move_san, get_latest_fen, get_move_count, is_game_over, parse_pgn_games
import settings

logger = logging.getLogger("monitor")

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
        initial_broadcast_id: str | None = None,
        initial_broadcast_url: str | None = None,
    ):
        self.bot = bot
        self.channel_id = channel_id
        self.groq_api_key = groq_api_key
        self.broadcast_id = initial_broadcast_id or None
        self.broadcast_url = initial_broadcast_url or ""
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

    def set_follow(self, broadcast_id: str, broadcast_url: str) -> None:
        self.broadcast_id = broadcast_id.strip()
        self.broadcast_url = broadcast_url.strip()
        self.rounds.clear()
        self.active_round_id = None
        self._moves_analysed = 0

    def start(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        self._round_check_task = loop.create_task(self._round_check_loop())
        self._poll_task = loop.create_task(self._poll_loop())

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
            "broadcast_id": self.broadcast_id or "—",
            "broadcast_url": self.broadcast_url or "—",
            "following": bool(self.broadcast_id),
        }

    async def _round_check_loop(self) -> None:
        await asyncio.sleep(3)
        while self._running:
            try:
                await self._check_rounds()
            except Exception:
                pass
            await asyncio.sleep(settings.ROUND_CHECK_INTERVAL_SECONDS)

    async def _check_rounds(self) -> None:
        if not self.broadcast_id:
            return

        rounds = await self.lichess.get_broadcast_rounds(self.broadcast_id)
        if not rounds:
            return

        now = datetime.now(timezone.utc)

        for round_info in rounds:
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
                except:
                    pass

            if round_id not in self.rounds:
                self.rounds[round_id] = RoundState(
                    round_id=round_id,
                    round_name=round_name,
                    start_time=start_time,
                )

            state = self.rounds[round_id]
            state.round_name = round_name
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
                    mins = max(1, int(secs_until // 60))
                    tour_json = await self.lichess.get_broadcast_tournament(self.broadcast_id)
                    tour_name = (tour_json.get("tour") or {}).get("name") or self.broadcast_id if tour_json else ""
                    await self._send_reminder(round_id, round_name, mins, self.broadcast_url, tour_name)

            if started and not finished and not state.start_announced:
                state.started = True
                state.start_announced = True
                self.active_round_id = round_id

            if started and not finished:
                self.active_round_id = round_id

    async def _poll_loop(self) -> None:
        await asyncio.sleep(5)
        while self._running:
            try:
                if self.broadcast_id and self.active_round_id:
                    await self._poll_active_round()
            except Exception:
                pass
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def _poll_active_round(self) -> None:
        round_id = self.active_round_id
        if not round_id:
            return

        pgn = await self.lichess.get_round_pgn(round_id)
        if not pgn:
            return

        games = parse_pgn_games(pgn)
        if not games:
            return

        round_state = self.rounds.get(round_id)
        if not round_state:
            return

        round_name = round_state.round_name

        for i, game in enumerate(games):
            game_id = get_game_id(game)

            try:
                board_num = int(game["headers"].get("Board", i + 1))
            except:
                board_num = i + 1

            if game_id not in round_state.games:
                round_state.games[game_id] = GameState(
                    game_id=game_id,
                    white=game["white"],
                    black=game["black"],
                    board_number=board_num,
                )

            gs = round_state.games[game_id]

            if gs.is_over:
                continue

            if is_game_over(game) and game_id not in round_state.finished_game_ids:
                gs.is_over = True
                round_state.finished_game_ids.add(game_id)
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

            (eval_after, mate_after, best_move, continuation), cloud_raw = await self._evaluate(
                latest_fen
            )
            self._moves_analysed += 1

            classification = classify_move(gs.last_eval, eval_after, turn_before)

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

    async def _evaluate(
        self, fen: str
    ) -> tuple[tuple[float | None, int | None, str, list[str]], dict | None]:
        cloud = await self.lichess.cloud_eval(fen, multi_pv=3)
        if cloud:
            return parse_cloud_eval(cloud), cloud
        fb = await evaluate_with_chess_api(fen)
        return fb, None

    async def _get_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
            except:
                return None
        return channel

    async def _send_reminder(
        self,
        round_id: str,
        round_name: str,
        minutes: int,
        broadcast_url: str,
        tour_name: str,
    ) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        commentary = await generate_reminder_message(
            round_name,
            minutes,
            self.groq_api_key,
            settings.GROQ_MODEL,
            tour_name,
        )

        embed = build_reminder_embed(
            round_name,
            minutes,
            commentary,
            self.broadcast_url,
            tour_name,
            "",
            "",
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

        eb = eval_before if eval_before is not None else 0.0
        ea = eval_after if eval_after is not None else 0.0
        winning_side = get_winning_side(eval_after, mate_after)
        commentary = await generate_move_commentary(
            white=game["white"],
            black=game["black"],
            round_name=round_name,
            move_san=move_san,
            classification=classification,
            eval_before=eb,
            eval_after=ea,
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
            eval_before=eb,
            eval_after=ea,
            mate_before=mate_before,
            mate_after=mate_after,
            top_move=best_move,
            continuation=continuation,
            commentary=commentary,
            lichess_url=self.broadcast_url,
        )

        await channel.send(embed=embed)
