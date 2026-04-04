"""
Lichess API client: broadcast endpoints (GET) + cloud eval.

Spec: https://lichess.org/api#tag/broadcasts
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import aiohttp

logger = logging.getLogger("maggie-man.lichess")


class LichessClient:
    def __init__(
        self,
        api_base: str,
        cloud_eval_url: str,
        site_base: str,
        oauth_token: str | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.cloud_eval_url = cloud_eval_url
        self.site_base = site_base.rstrip("/")
        self.oauth_token = oauth_token
        self.session: aiohttp.ClientSession | None = None

    def _auth_headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.oauth_token:
            h["Authorization"] = f"Bearer {self.oauth_token}"
        return h

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "MaggieManBot/1.0 (Discord Chess Bot)",
                    **self._auth_headers(),
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _get_json(self, url: str, **kwargs: Any) -> Any | None:
        try:
            session = await self._get_session()
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                logger.warning("GET %s → HTTP %s: %s", url, resp.status, body[:300])
                return None
        except Exception as e:
            logger.error("GET %s error: %s", url, e, exc_info=True)
            return None

    async def _get_text(self, url: str, **kwargs: Any) -> str | None:
        try:
            session = await self._get_session()
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.text()
                body = await resp.text()
                logger.warning("GET %s → HTTP %s: %s", url, resp.status, body[:200])
                return None
        except Exception as e:
            logger.error("GET %s error: %s", url, e, exc_info=True)
            return None

    # --- GET /api/broadcast (official, NDJSON stream) ---

    async def get_official_broadcasts(self, nb: int = 20, html: bool = False) -> list[dict]:
        """Parse NDJSON stream into a list (caps at nb lines)."""
        url = f"{self.api_base}/broadcast"
        params: dict[str, str | int] = {"nb": max(1, min(100, nb))}
        if html:
            params["html"] = "true"
        out: list[dict] = []
        try:
            session = await self._get_session()
            async with session.get(
                url,
                params=params,
                headers={"Accept": "application/x-ndjson"},
            ) as resp:
                if resp.status != 200:
                    logger.warning("official broadcasts HTTP %s", resp.status)
                    return []
                text = await resp.text()
                for line in text.splitlines():
                    if len(out) >= nb:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error("get_official_broadcasts: %s", e, exc_info=True)
        return out

    # --- GET /api/broadcast/top ---

    async def get_broadcast_top(self, page: int = 1, html: bool = False) -> dict | None:
        url = f"{self.api_base}/broadcast/top"
        params: dict[str, str | int] = {"page": max(1, min(20, page))}
        if html:
            params["html"] = "true"
        return await self._get_json(url, params=params, headers={"Accept": "application/json"})

    # --- GET /api/broadcast/by/{username} ---

    async def get_broadcasts_by_user(
        self, username: str, page: int = 1, html: bool = False
    ) -> dict | None:
        url = f"{self.api_base}/broadcast/by/{username}"
        params: dict[str, str | int] = {"page": max(1, page)}
        if html:
            params["html"] = "true"
        return await self._get_json(url, params=params, headers={"Accept": "application/json"})

    # --- GET /api/broadcast/search ---

    async def search_broadcasts(self, q: str, page: int = 1) -> dict | None:
        url = f"{self.api_base}/broadcast/search"
        params = {"q": q, "page": max(1, min(20, page))}
        return await self._get_json(url, params=params, headers={"Accept": "application/json"})

    # --- GET /api/broadcast/{broadcastTournamentId} ---

    async def get_broadcast_tournament(self, broadcast_tournament_id: str) -> dict | None:
        tid = broadcast_tournament_id.strip()
        if len(tid) != 8:
            logger.warning("broadcast tournament id should be 8 chars, got %r", tid)
        url = f"{self.api_base}/broadcast/{tid}"
        return await self._get_json(url, headers={"Accept": "application/json"})

    async def get_broadcast_with_rounds(self, broadcast_tournament_id: str | None = None) -> dict | None:
        """Alias used by monitor: fetch tournament + rounds."""
        bid = (broadcast_tournament_id or "").strip()
        if not bid:
            return None
        return await self.get_broadcast_tournament(bid)

    async def get_broadcast_rounds(self, broadcast_tournament_id: str | None = None) -> list[dict]:
        data = await self.get_broadcast_with_rounds(broadcast_tournament_id)
        if not data:
            return []
        return data.get("rounds", [])

    # --- GET /api/broadcast/{slug}/{roundSlug}/{roundId} ---

    async def get_broadcast_round(
        self,
        broadcast_round_id: str,
        broadcast_tournament_slug: str = "-",
        broadcast_round_slug: str = "-",
    ) -> dict | None:
        rid = broadcast_round_id.strip()
        url = (
            f"{self.api_base}/broadcast/"
            f"{broadcast_tournament_slug}/{broadcast_round_slug}/{rid}"
        )
        return await self._get_json(url, headers={"Accept": "application/json"})

    # --- GET /api/broadcast/round/{roundId}.pgn ---

    async def get_round_pgn(
        self,
        round_id: str,
        clocks: bool = True,
        comments: bool = True,
    ) -> str | None:
        url = f"{self.api_base}/broadcast/round/{round_id}.pgn"
        params = {"clocks": str(clocks).lower(), "comments": str(comments).lower()}
        return await self._get_text(
            url,
            params=params,
            headers={"Accept": "application/x-chess-pgn"},
        )

    # --- GET /api/broadcast/{broadcastTournamentId}.pgn ---

    async def get_tournament_pgn(
        self,
        broadcast_tournament_id: str,
        clocks: bool = True,
        comments: bool = True,
    ) -> str | None:
        tid = broadcast_tournament_id.strip()
        url = f"{self.api_base}/broadcast/{tid}.pgn"
        params = {"clocks": str(clocks).lower(), "comments": str(comments).lower()}
        return await self._get_text(
            url,
            params=params,
            headers={"Accept": "application/x-chess-pgn"},
        )

    # --- GET /api/stream/broadcast/round/{roundId}.pgn (streaming) ---

    async def stream_round_pgn_lines(
        self,
        round_id: str,
        clocks: bool = True,
        comments: bool = True,
    ) -> AsyncIterator[str]:
        """
        Yield text chunks from the live PGN stream. Caller must cancel the task to stop.
        https://lichess.org/api#tag/broadcasts/GET/api/stream/broadcast/round/{broadcastRoundId}.pgn
        """
        url = f"{self.api_base}/stream/broadcast/round/{round_id}.pgn"
        params = {"clocks": str(clocks).lower(), "comments": str(comments).lower()}
        session = await self._get_session()
        try:
            async with session.get(
                url,
                params=params,
                headers={"Accept": "application/x-chess-pgn"},
            ) as resp:
                if resp.status != 200:
                    return
                async for chunk in resp.content.iter_chunked(8192):
                    yield chunk.decode("utf-8", errors="replace")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("stream_round_pgn_lines: %s", e, exc_info=True)

    # --- Site paths under /broadcast/{id}/... (not under /api/) ---

    async def get_broadcast_players(self, broadcast_tournament_id: str) -> list | None:
        tid = broadcast_tournament_id.strip()
        url = f"{self.site_base}/broadcast/{tid}/players"
        data = await self._get_json(url, headers={"Accept": "application/json"})
        return data if isinstance(data, list) else None

    async def get_broadcast_player(
        self, broadcast_tournament_id: str, player_id: str
    ) -> dict | None:
        tid = broadcast_tournament_id.strip()
        pid = player_id.strip()
        url = f"{self.site_base}/broadcast/{tid}/players/{pid}"
        data = await self._get_json(url, headers={"Accept": "application/json"})
        return data if isinstance(data, dict) else None

    async def get_broadcast_team_standings(self, broadcast_tournament_id: str) -> list | None:
        tid = broadcast_tournament_id.strip()
        url = f"{self.site_base}/broadcast/{tid}/teams/standings"
        data = await self._get_json(url, headers={"Accept": "application/json"})
        return data if isinstance(data, list) else None

    # --- GET /api/broadcast/my-rounds (OAuth) ---

    async def get_my_broadcast_rounds(self, nb: int = 20) -> list[dict]:
        """Requires LICHESS_API_TOKEN with study:read."""
        if not self.oauth_token:
            return []
        url = f"{self.api_base}/broadcast/my-rounds"
        params = {"nb": max(1, nb)}
        out: list[dict] = []
        try:
            session = await self._get_session()
            async with session.get(
                url,
                params=params,
                headers={"Accept": "application/x-ndjson", **self._auth_headers()},
            ) as resp:
                if resp.status != 200:
                    logger.warning("my-rounds HTTP %s", resp.status)
                    return []
                text = await resp.text()
                for line in text.splitlines():
                    if len(out) >= nb:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error("get_my_broadcast_rounds: %s", e, exc_info=True)
        return out

    # --- Cloud eval ---

    async def cloud_eval(self, fen: str, multi_pv: int = 3) -> dict | None:
        params = {"fen": fen, "multiPv": str(multi_pv)}
        try:
            session = await self._get_session()
            async with session.get(
                self.cloud_eval_url,
                params=params,
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 404:
                    logger.debug("cloud_eval: cache miss (404)")
                    return None
                logger.warning("cloud_eval: HTTP %s", resp.status)
                return None
        except asyncio.TimeoutError:
            logger.warning("cloud_eval: timed out")
            return None
        except Exception as e:
            logger.error("cloud_eval error: %s", e)
            return None
