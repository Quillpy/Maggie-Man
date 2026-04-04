"""
Diagnostic script — run this BEFORE starting the bot.
Usage: python diagnose.py
"""

import asyncio
import aiohttp
import json
import re

CANDIDATES_BROADCAST_ID = "OqKQ3sJH"
LICHESS_API_BASE = "https://lichess.org/api"
LICHESS_CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"
CHESS_API_URL = "https://chess-api.com/v1"
TEST_FEN = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


async def check_lichess_broadcast():
    print("\n[1] Lichess Broadcast Tournament + Rounds")
    url = f"{LICHESS_API_BASE}/broadcast/{CANDIDATES_BROADCAST_ID}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"Accept": "application/json"},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                print(f"    HTTP {r.status}  →  {url}")
                if r.status == 200:
                    data = await r.json()
                    tour = data.get("tour", {})
                    rounds = data.get("rounds", [])
                    print(f"    ✅ Tournament: {tour.get('name', '?')}")
                    print(f"    ✅ Rounds: {len(rounds)}")
                    active_round_id = None
                    for rd in rounds:
                        ongoing  = rd.get("ongoing", False)
                        finished = rd.get("finished", False)
                        starts   = rd.get("startsAt", "")
                        status = "🟢 LIVE" if ongoing else ("✅ done" if finished else "⏳ upcoming")
                        print(f"       {status}  {rd.get('name','?'):15s}  id={rd.get('id')}  startsAt={starts}")
                        if ongoing and not finished:
                            active_round_id = rd.get("id")
                    if active_round_id:
                        await check_round_pgn(active_round_id)
                    else:
                        print("\n    ℹ️  No round currently live (between rounds or tournament not started)")
                else:
                    body = await r.text()
                    print(f"    ❌ {body[:300]}")
    except Exception as e:
        print(f"    ❌ Exception: {e}")


async def check_round_pgn(round_id: str):
    print(f"\n[2] Round PGN  (round_id={round_id})")
    url = f"{LICHESS_API_BASE}/broadcast/round/{round_id}.pgn"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"Accept": "application/x-chess-pgn"},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                print(f"    HTTP {r.status}  →  {url}")
                if r.status == 200:
                    text = await r.text()
                    games = [g for g in re.split(r'\n\n(?=\[)', text.strip()) if g.strip()]
                    fens  = re.findall(r'\[%fen ([^\]]+)\]', text)
                    print(f"    ✅ {len(games)} games, {len(fens)} FEN annotations, {len(text)} chars")
                    if games:
                        hdrs = dict(re.findall(r'\[(\w+)\s+"([^"]*)"\]', games[0]))
                        print(f"       Sample game: {hdrs.get('White','?')} vs {hdrs.get('Black','?')}  Board={hdrs.get('Board','?')}")
                    if fens:
                        print(f"       Last FEN: {fens[-1][:70]}")
                else:
                    body = await r.text()
                    print(f"    ❌ {body[:200]}")
    except Exception as e:
        print(f"    ❌ Exception: {e}")


async def check_cloud_eval():
    print(f"\n[3] Lichess Cloud Eval")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(LICHESS_CLOUD_EVAL_URL,
                             params={"fen": TEST_FEN, "multiPv": "3"},
                             headers={"Accept": "application/json"},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    data = await r.json()
                    pvs = data.get("pvs", [])
                    print(f"    ✅ depth={data.get('depth','?')}, {len(pvs)} PV(s)")
                    for i, pv in enumerate(pvs):
                        cp   = pv.get("cp")
                        mate = pv.get("mate")
                        score = f"mate {mate}" if mate is not None else f"{cp/100:+.2f}"
                        print(f"       PV{i+1}: {score}  {pv.get('moves','')[:50]}")
                elif r.status == 404:
                    print("    ℹ️  Position not in cache (normal for rare positions)")
                else:
                    print(f"    ❌ HTTP {r.status}")
    except Exception as e:
        print(f"    ❌ Exception: {e}")


async def check_chess_api():
    print(f"\n[4] chess-api.com Fallback")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(CHESS_API_URL, json={"fen": TEST_FEN, "depth": 12},
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    d = await r.json()
                    print(f"    ✅ type={d.get('type')} eval={d.get('eval')} move={d.get('san')} depth={d.get('depth')}")
                else:
                    print(f"    ❌ HTTP {r.status}")
    except Exception as e:
        print(f"    ❌ Exception: {e}")


async def check_discord():
    print(f"\n[5] Discord Channel + Bot Token")
    from config import DISCORD_BOT_TOKEN, DISCORD_CHESS_CHANNEL_ID
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://discord.com/api/v10/channels/{DISCORD_CHESS_CHANNEL_ID}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                print(f"    HTTP {r.status}")
                if r.status == 200:
                    d = await r.json()
                    print(f"    ✅ Channel: #{d.get('name')} (guild {d.get('guild_id')})")
                elif r.status == 401:
                    print("    ❌ Invalid bot token")
                elif r.status == 403:
                    print("    ❌ Bot lacks permission to view this channel")
                elif r.status == 404:
                    print("    ❌ Channel not found — check DISCORD_CHESS_CHANNEL_ID")
                else:
                    print(f"    ❌ HTTP {r.status}")
    except Exception as e:
        print(f"    ❌ Exception: {e}")


async def main():
    print("=" * 60)
    print("  Maggie Man Bot — Pre-flight Diagnostics")
    print("=" * 60)
    await check_lichess_broadcast()
    await check_cloud_eval()
    await check_chess_api()
    await check_discord()
    print("\n" + "=" * 60)
    print("  Done. Fix any ❌ before running bot.py")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())