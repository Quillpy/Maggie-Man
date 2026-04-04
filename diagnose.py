"""
Pre-flight checks. Does not import bot settings (so you can run without Discord env).
Usage: python diagnose.py
"""

from __future__ import annotations

import asyncio
import os
import re

import aiohttp
from dotenv import load_dotenv

load_dotenv()

LICHESS_API_BASE = os.getenv("LICHESS_API_BASE", "https://lichess.org/api").rstrip("/")
LICHESS_CLOUD_EVAL_URL = f"{LICHESS_API_BASE}/cloud-eval"
CHESS_API_URL = "https://chess-api.com/v1"
TEST_FEN = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
MONITORED_BROADCAST_ID = os.getenv("MONITORED_BROADCAST_ID", "OqKQ3sJH").strip()


async def check_lichess_broadcast() -> None:
    print("\n[1] Lichess broadcast tournament + rounds")
    url = f"{LICHESS_API_BASE}/broadcast/{MONITORED_BROADCAST_ID}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                print(f"    HTTP {r.status}  →  {url}")
                if r.status == 200:
                    data = await r.json()
                    tour = data.get("tour", {})
                    rounds = data.get("rounds", [])
                    print(f"    OK Tournament: {tour.get('name', '?')}")
                    print(f"    OK Rounds: {len(rounds)}")
                    active_round_id = None
                    for rd in rounds:
                        ongoing = rd.get("ongoing", False)
                        finished = rd.get("finished", False)
                        starts = rd.get("startsAt", "")
                        status = "LIVE" if ongoing else ("done" if finished else "upcoming")
                        print(
                            f"       {status:8}  {rd.get('name', '?'):15}  id={rd.get('id')}  startsAt={starts}"
                        )
                        if ongoing and not finished:
                            active_round_id = rd.get("id")
                    if active_round_id:
                        await check_round_pgn(active_round_id)
                    else:
                        print("\n    No round marked ongoing right now (normal between rounds).")
                else:
                    body = await r.text()
                    print(f"    FAIL {body[:300]}")
    except Exception as e:
        print(f"    FAIL {e}")


async def check_round_pgn(round_id: str) -> None:
    print(f"\n[2] Round PGN  (round_id={round_id})")
    url = f"{LICHESS_API_BASE}/broadcast/round/{round_id}.pgn"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"Accept": "application/x-chess-pgn"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                print(f"    HTTP {r.status}  →  {url}")
                if r.status == 200:
                    text = await r.text()
                    games = [g for g in re.split(r"\n\n(?=\[)", text.strip()) if g.strip()]
                    fens = re.findall(r"\[%fen ([^\]]+)\]", text)
                    print(f"    OK {len(games)} games, {len(fens)} FEN tags, {len(text)} chars")
                else:
                    body = await r.text()
                    print(f"    FAIL {body[:200]}")
    except Exception as e:
        print(f"    FAIL {e}")


async def check_broadcast_search() -> None:
    print("\n[3] Broadcast search API")
    url = f"{LICHESS_API_BASE}/broadcast/search"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                params={"q": "candidates", "page": 1},
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    data = await r.json()
                    n = len(data.get("currentPageResults") or [])
                    print(f"    OK {n} result(s) on page 1")
                else:
                    print(f"    FAIL {await r.text()[:200]}")
    except Exception as e:
        print(f"    FAIL {e}")


async def check_cloud_eval() -> None:
    print(f"\n[4] Lichess cloud-eval")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                LICHESS_CLOUD_EVAL_URL,
                params={"fen": TEST_FEN, "multiPv": "3"},
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    data = await r.json()
                    print(f"    OK depth={data.get('depth', '?')}")
                elif r.status == 404:
                    print("    OK (404 cache miss is normal)")
                else:
                    print(f"    FAIL")
    except Exception as e:
        print(f"    FAIL {e}")


async def check_chess_api() -> None:
    print(f"\n[5] chess-api.com fallback")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                CHESS_API_URL,
                json={"fen": TEST_FEN, "depth": 12},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    d = await r.json()
                    print(f"    OK eval={d.get('eval')} move={d.get('san')}")
                else:
                    print("    FAIL")
    except Exception as e:
        print(f"    FAIL {e}")


async def check_discord() -> None:
    print(f"\n[6] Discord (optional)")
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.getenv("DISCORD_CHESS_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        print("    SKIP set DISCORD_BOT_TOKEN and DISCORD_CHESS_CHANNEL_ID in .env")
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://discord.com/api/v10/channels/{channel_id}",
                headers={"Authorization": f"Bot {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    d = await r.json()
                    print(f"    OK #{d.get('name')} (guild {d.get('guild_id')})")
                elif r.status == 401:
                    print("    FAIL invalid bot token")
                elif r.status == 403:
                    print("    FAIL missing access to channel")
                elif r.status == 404:
                    print("    FAIL channel id wrong")
                else:
                    print("    FAIL")
    except Exception as e:
        print(f"    FAIL {e}")


async def main() -> None:
    print("=" * 60)
    print("  Maggie Man — diagnostics")
    print("=" * 60)
    await check_lichess_broadcast()
    await check_broadcast_search()
    await check_cloud_eval()
    await check_chess_api()
    await check_discord()
    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
