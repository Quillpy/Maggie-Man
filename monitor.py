"""
Tournament Monitor — core polling engine for Maggie Man.

Flow:
1. Every 10s: fetch PGN for the active round
2. Parse all games (up to 16) and detect new moves
3. Evaluate new positions via Lichess Cloud Eval (falls back to chess-api.com)
4. Classify: blunder / mistake / brilliancy
5. If alert-worthy: generate Groq commentary + send Discord embed

Round management:
- Poll /broadcast rounds list every 2 minutes
- Detect when a new round becomes active
- Send 60-min reminder before round starts
- Send round-start announcement with pairings
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import discord

from lichess_client import LichessClient
from pgn_parser import parse_pgn_games, get_game_id, get_latest_fen, get_move_count, get_last_move_san, is_game_over
from chess_engine import (
    classify_move, is_alert_worthy, format_eval, get_winning_side,
    parse_cloud_eval, evaluate_with_chess_api,
)
from groq_commentary import generate_move_commentary, generate_round_start_message, generate_reminder_message
from embeds import build_move_embed, build_round_start_embed, build_reminder_embed, build_game_over_embed
from config import POLL_INTERVAL_SECONDS, REMINDER_MINUTES_BEFORE

logger = logging.getLogger("maggie-man.monitor")

BROADCAST_URL = "https://lichess.org/broadcast/fide-candidates-2026--combined-open--women/OqKQ3sJH"


@dataclass
class GameState:
    game_id: str
    white: str
    black: str
    move_count: int = 0
    last_fen: str = ""
    last_eval: float | None = None   # pawns, white POV; None = not yet evaluated
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
    games: dict = field(default_factory=dict)           # game_id → GameState
    finished_game_ids: set = field(default_factory=set)


class TournamentMonitor:
    def __init__(self, bot: discord.Client, channel_id: int, groq_api_key: str):
        self.bot = bot
        self.channel_id = channel_id
        self.groq_api_key = groq_api_key
        self.lichess = LichessClient()
        self.followers: set[int] = set()

        self.rounds: dict[str, RoundState] = {}
        self.active_round_id: str | None = None
        self._running = False
        self._moves_analysed = 0

        self._poll_task: asyncio.Task | None = None
        self._round_check_task: asyncio.Task | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start background tasks. Must be called from within a running event loop."""
        self._running = True
        loop = asyncio.get_running_loop()   # ← correct; get_event_loop() is deprecated
        self._round_check_task = loop.create_task(self._round_check_loop())
        self._poll_task = loop.create_task(self._poll_loop())
        logger.info("Monitor tasks started (round check + game poll)")

    def stop(self):
        self._running = False
        for t in (self._poll_task, self._round_check_task):
            if t:
                t.cancel()

    def add_follower(self, user_id: int):
        self.followers.add(user_id)
        logger.info(f"Follower added: {user_id} (total: {len(self.followers)})")

    def remove_follower(self, user_id: int):
        self.followers.discard(user_id)

    def get_status(self) -> dict:
        active_games = 0
        if self.active_round_id and self.active_round_id in self.rounds:
            active_games = len(self.rounds[self.active_round_id].games)
        return {
            "running": self._running,
            "followers": len(self.followers),
            "active_games": active_games,
            "rounds_tracked": len(self.rounds),
            "moves_analysed": self._moves_analysed,
            "active_round": self.active_round_id,
        }

    # ── Round check loop (every 2 min) ────────────────────────────────────────

    async def _round_check_loop(self):
        """Periodically check for upcoming/started rounds."""
        # First check immediately on startup so the bot detects an already-running round
        await asyncio.sleep(3)
        while self._running:
            try:
                await self._check_rounds()
            except Exception as e:
                logger.error(f"Round check error: {e}", exc_info=True)
            await asyncio.sleep(120)

    async def _check_rounds(self):
        rounds = await self.lichess.get_broadcast_rounds()
        if not rounds:
            logger.warning("_check_rounds: received empty rounds list")
            return

        now = datetime.now(timezone.utc)

        for r in rounds:
            # Rounds from GET /api/broadcast/{id} are flat dicts:
            # { "id": "...", "name": "Round 5", "ongoing": true, "finished": false, ... }
            round_info = r   # flat — no nesting under "round" key
            round_id = round_info.get("id")
            if not round_id:
                logger.debug(f"Skipping entry with no round id: {list(r.keys())}")
                continue

            round_name = round_info.get("name", f"Round {round_id}")
            # Lichess uses "ongoing" not "started" in some versions; handle both
            started  = round_info.get("ongoing", False) or round_info.get("started", False)
            finished = round_info.get("finished", False)
            start_ts = round_info.get("startsAt")   # millisecond epoch or absent

            # Parse start time
            start_time = None
            if start_ts:
                try:
                    start_time = datetime.fromtimestamp(int(start_ts) / 1000, tz=timezone.utc)
                except Exception as e:
                    logger.warning(f"Could not parse startsAt={start_ts}: {e}")

            # Init round state
            if round_id not in self.rounds:
                logger.info(f"Discovered new round: {round_name} (id={round_id}, started={started}, finished={finished})")
                self.rounds[round_id] = RoundState(
                    round_id=round_id,
                    round_name=round_name,
                    start_time=start_time,
                )

            state = self.rounds[round_id]
            state.start_time = start_time

            # ── 1-hour reminder ──────────────────────────────────────────────
            if (
                not state.reminder_sent
                and not started
                and not finished
                and start_time
            ):
                secs_until = (start_time - now).total_seconds()
                if 0 < secs_until <= REMINDER_MINUTES_BEFORE * 60:
                    state.reminder_sent = True
                    mins = int(secs_until // 60)
                    logger.info(f"Sending reminder for {round_name} ({mins}min away)")
                    await self._send_reminder(round_name, mins)

            # ── Round start announcement ─────────────────────────────────────
            if started and not finished and not state.start_announced:
                state.started = True
                state.start_announced = True
                self.active_round_id = round_id
                logger.info(f"Round started: {round_name} (id={round_id})")

                # Fetch pairings from PGN
                pgn = await self.lichess.get_round_pgn(round_id)
                pairings = []
                if pgn:
                    games = parse_pgn_games(pgn)
                    for i, g in enumerate(games):
                        try:
                            board = int(g["headers"].get("Board", i + 1))
                        except (ValueError, TypeError):
                            board = i + 1
                        pairings.append({
                            "white": g["white"],
                            "black": g["black"],
                            "board": board,
                        })
                await self._send_round_start(round_name, pairings)

            # Keep tracking the most-recently-started unfinished round
            if started and not finished:
                self.active_round_id = round_id

    # ── Game poll loop (every 10s) ────────────────────────────────────────────

    async def _poll_loop(self):
        """Poll the active round for new moves every 10 seconds."""
        await asyncio.sleep(5)  # slight offset from round-check startup
        while self._running:
            try:
                if self.active_round_id:
                    await self._poll_active_round()
                else:
                    logger.debug("_poll_loop: no active round yet, waiting...")
            except Exception as e:
                logger.error(f"Poll loop error: {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _poll_active_round(self):
        round_id = self.active_round_id
        pgn = await self.lichess.get_round_pgn(round_id)
        if not pgn:
            return

        games = parse_pgn_games(pgn)
        if not games:
            logger.debug(f"_poll_active_round: no games parsed from PGN")
            return

        round_state = self.rounds.get(round_id)
        if not round_state:
            # Round appeared in poll before round-check registered it; init now
            round_state = RoundState(round_id=round_id, round_name=f"Round {round_id}")
            self.rounds[round_id] = round_state

        round_name = round_state.round_name

        for i, game in enumerate(games):
            game_id = get_game_id(game)

            try:
                board_num = int(game["headers"].get("Board", i + 1))
            except (ValueError, TypeError):
                board_num = i + 1

            # Init game state on first sight
            if game_id not in round_state.games:
                round_state.games[game_id] = GameState(
                    game_id=game_id,
                    white=game["white"],
                    black=game["black"],
                    board_number=board_num,
                )
                logger.info(f"Tracking new game: Board {board_num} {game['white']} vs {game['black']}")

            gs = round_state.games[game_id]

            if gs.is_over:
                continue

            # ── Game over ────────────────────────────────────────────────────
            if is_game_over(game) and game_id not in round_state.finished_game_ids:
                gs.is_over = True
                round_state.finished_game_ids.add(game_id)
                await self._send_game_over(game, gs, round_name)
                continue

            # ── New move detection ───────────────────────────────────────────
            current_move_count = get_move_count(game)
            if current_move_count <= gs.move_count:
                continue  # No new moves

            gs.move_count = current_move_count
            latest_fen = get_latest_fen(game)
            last_move_san = get_last_move_san(game)

            if not latest_fen or not last_move_san:
                logger.debug(f"No FEN/SAN available yet for {game['white']} vs {game['black']}")
                continue

            # Whose turn was it BEFORE this move?
            # After white's move: total plies = odd  → turn_before = 'w'
            # After black's move: total plies = even → turn_before = 'b'
            turn_before = "w" if (current_move_count % 2 == 1) else "b"
            move_number = (current_move_count + 1) // 2

            logger.info(
                f"[{round_name}] Board {board_num} {game['white']} vs {game['black']}"
                f" | move {move_number}: {last_move_san} (ply {current_move_count})"
            )

            # ── Engine evaluation ────────────────────────────────────────────
            eval_after, mate_after, best_move, continuation = await self._evaluate(latest_fen)
            self._moves_analysed += 1

            # ── Classification ───────────────────────────────────────────────
            classification = classify_move(gs.last_eval, eval_after, turn_before)

            logger.info(
                f"  → eval: {format_eval(gs.last_eval, gs.last_mate)} → {format_eval(eval_after, mate_after)}"
                f" | classification: {classification}"
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

            # Update tracked state
            gs.last_fen = latest_fen
            gs.last_eval = eval_after
            gs.last_mate = mate_after

    async def _evaluate(self, fen: str) -> tuple:
        """
        Evaluate a position.
        First tries Lichess Cloud Eval (cached, high depth, fast).
        Falls back to chess-api.com if position not in cache.
        Returns (eval_pawns, mate, best_move, continuation).
        """
        # Try Lichess Cloud Eval first
        cloud = await self.lichess.cloud_eval(fen, multi_pv=3)
        if cloud:
            ev, mate, best, cont = parse_cloud_eval(cloud)
            depth = cloud.get("depth", "?")
            logger.debug(f"Cloud eval: depth={depth}, eval={ev}, mate={mate}, best={best}")
            return ev, mate, best, cont

        # Fallback to chess-api.com
        logger.debug("Cloud eval cache miss — falling back to chess-api.com")
        return await evaluate_with_chess_api(fen)

    # ── Senders ───────────────────────────────────────────────────────────────

    async def _get_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error(f"Cannot get channel {self.channel_id}: {e}")
                return None
        return channel

    def _mention_followers(self) -> str | None:
        if not self.followers:
            return None
        return " ".join(f"<@{uid}>" for uid in self.followers)

    async def _send_reminder(self, round_name: str, minutes: int):
        channel = await self._get_channel()
        if not channel:
            return
        commentary = await generate_reminder_message(round_name, minutes, self.groq_api_key)
        embed = build_reminder_embed(round_name, minutes, commentary)
        await channel.send(content=self._mention_followers(), embed=embed)
        logger.info(f"Sent reminder: {round_name} in {minutes}min")

    async def _send_round_start(self, round_name: str, pairings: list[dict]):
        channel = await self._get_channel()
        if not channel:
            return
        commentary = await generate_round_start_message(round_name, pairings, self.groq_api_key)
        embed = build_round_start_embed(round_name, pairings, commentary, BROADCAST_URL)
        await channel.send(content=self._mention_followers(), embed=embed)
        logger.info(f"Sent round start: {round_name} with {len(pairings)} pairings")

    async def _send_move_alert(
        self, game, gs, round_name, move_san, move_number,
        classification, eval_before, eval_after, mate_before,
        mate_after, best_move, continuation,
    ):
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
            lichess_url=game.get("site", BROADCAST_URL),
        )

        await channel.send(embed=embed)
        logger.info(f"Alert sent: {classification} — {game['white']} vs {game['black']} — {move_san}")

    async def _send_game_over(self, game: dict, gs: GameState, round_name: str):
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
        logger.info(f"Game over: {game['white']} vs {game['black']} — {game['result']}")