from __future__ import annotations

import aiohttp
from typing import Any

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
                    "User-Agent": "MaggieManBot/1.0",
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
                return None
        except Exception:
            return None

    async def _get_text(self, url: str, **kwargs: Any) -> str | None:
        try:
            session = await self._get_session()
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None
        except Exception:
            return None

    async def search_broadcasts(self, q: str, page: int = 1) -> dict | None:
        url = f"{self.api_base}/broadcast/search"
        params = {"q": q, "page": max(1, min(20, page))}
        return await self._get_json(url, params=params, headers={"Accept": "application/json"})

    async def get_broadcast_tournament(self, broadcast_tournament_id: str) -> dict | None:
        tid = broadcast_tournament_id.strip()
        url = f"{self.api_base}/broadcast/{tid}"
        return await self._get_json(url, headers={"Accept": "application/json"})

    async def get_broadcast_rounds(self, broadcast_tournament_id: str) -> list[dict]:
        data = await self.get_broadcast_tournament(broadcast_tournament_id.strip())
        if not data:
            return []
        return data.get("rounds", [])

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
                return None
        except Exception:
            return None
