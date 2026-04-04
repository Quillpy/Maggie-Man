"""
Lichess API client for fetching broadcast/tournament data.
No auth token needed for public broadcast endpoints.

Correct endpoints (verified from Lichess API spec):
  GET /api/broadcast/{broadcastTournamentId}
      → Returns tournament + embedded rounds array (JSON)
  GET /api/broadcast/{tournSlug}/{roundSlug}/{roundId}
      → Returns a single round's metadata + games (slugs can be "-")
  GET /api/broadcast/round/{roundId}.pgn
      → Multi-game PGN for all games in a round
  GET /api/cloud-eval?fen=...&multiPv=N
      → Lichess cached Stockfish cloud evaluation
"""

import aiohttp
import asyncio
import json
import logging
from config import LICHESS_API_BASE, CANDIDATES_BROADCAST_ID, LICHESS_CLOUD_EVAL_URL

logger = logging.getLogger("maggie-man.lichess")


class LichessClient:
    def __init__(self):
        self.base = LICHESS_API_BASE
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "MaggieManBot/1.0 (Discord Chess Bot)"},
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ── Broadcast tournament (includes rounds list) ───────────────────────────

    async def get_broadcast_with_rounds(self) -> dict | None:
        """
        GET /api/broadcast/{broadcastTournamentId}

        Returns the full tournament object including a 'rounds' array.
        Each round in the array has shape:
        {
          "id": "jUqeCOHI",
          "name": "Round 5",
          "slug": "round-5",
          "url": "https://lichess.org/broadcast/.../round-5/jUqeCOHI",
          "createdAt": 1234567890000,
          "startsAt": 1234567890000,   # ms epoch, may be absent
          "ongoing": true,
          "finished": false
        }
        """
        url = f"{self.base}/broadcast/{CANDIDATES_BROADCAST_ID}"
        try:
            session = await self._get_session()
            async with session.get(url, headers={"Accept": "application/json"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rounds = data.get("rounds", [])
                    logger.info(f"get_broadcast_with_rounds: got {len(rounds)} rounds")
                    return data
                body = await resp.text()
                logger.warning(f"get_broadcast_with_rounds: HTTP {resp.status} → {body[:300]}")
                return None
        except Exception as e:
            logger.error(f"get_broadcast_with_rounds error: {e}", exc_info=True)
            return None

    async def get_broadcast_rounds(self) -> list[dict]:
        """
        Convenience wrapper — returns just the rounds list from the tournament.
        Each item is a round dict with id, name, ongoing, finished, startsAt etc.
        """
        data = await self.get_broadcast_with_rounds()
        if not data:
            return []
        return data.get("rounds", [])

    # ── Round PGN ─────────────────────────────────────────────────────────────

    async def get_round_pgn(self, round_id: str) -> str | None:
        """
        GET /api/broadcast/round/{roundId}.pgn

        Returns multi-game PGN for all games in a round.
        Lichess embeds FEN annotations as { [%fen <FEN>] } in move comments
        so we never need to replay moves to get the current position.

        round_id is the 8-character round ID, e.g. "jUqeCOHI"
        """
        url = f"{self.base}/broadcast/round/{round_id}.pgn"
        try:
            session = await self._get_session()
            async with session.get(url, headers={"Accept": "application/x-chess-pgn"}) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    logger.debug(f"get_round_pgn({round_id}): {len(text)} chars")
                    return text
                body = await resp.text()
                logger.warning(f"get_round_pgn({round_id}): HTTP {resp.status} → {body[:200]}")
                return None
        except Exception as e:
            logger.error(f"get_round_pgn({round_id}) error: {e}", exc_info=True)
            return None

    # ── Lichess Cloud Eval ────────────────────────────────────────────────────

    async def cloud_eval(self, fen: str, multi_pv: int = 3) -> dict | None:
        """
        GET /api/cloud-eval?fen=<fen>&multiPv=<n>

        Returns cached Stockfish analysis. Returns None on cache miss (HTTP 404).

        Response (200):
        {
          "fen": "...",
          "knodes": 45000,
          "depth": 24,
          "pvs": [
            { "moves": "e2e4 e7e5 g1f3", "cp": 30 },   ← centipawns, white POV
            { "moves": "d2d4 d7d5", "cp": 15 },
            { "moves": "c2c4 e7e5", "mate": 3 }         ← forced mate
          ]
        }
        cp is always from white's perspective.
        """
        params = {"fen": fen, "multiPv": str(multi_pv)}
        try:
            session = await self._get_session()
            async with session.get(
                LICHESS_CLOUD_EVAL_URL,
                params=params,
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 404:
                    logger.debug("cloud_eval: position not in cache (404)")
                    return None
                logger.warning(f"cloud_eval: HTTP {resp.status}")
                return None
        except asyncio.TimeoutError:
            logger.warning("cloud_eval: timed out")
            return None
        except Exception as e:
            logger.error(f"cloud_eval error: {e}")
            return None