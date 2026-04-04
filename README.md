# ♟️ Maggie Man — FIDE Candidates 2026 Discord Bot

> *"I'm Maggie Man, rated 2800+. These candidates are basically playing checkers."*

A parody of Magnus Carlsen who watches the FIDE Candidates 2026 tournament, roasts players on blunders, and sends critical move alerts to your Discord server.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify everything works (run this first!)
python diagnose.py

# 3. Start the bot
python bot.py
```

---

## Slash Commands

| Command | Description |
|---|---|
| `/follow` | Subscribe to tournament alerts (reminders, round starts, move alerts) |
| `/unfollow` | Unsubscribe |
| `/status` | Show monitor status (active round, games tracked, moves analysed) |
| `/maggie <question>` | Ask Maggie Man anything about chess |

---

## What the Bot Does

```
Every 2 minutes:
  → Fetch Lichess broadcast rounds list (NDJSON)
  → If round starts in ≤60min and not reminded yet → send @follower reminder
  → If round just started (ongoing=true) → send pairings embed with Maggie Man intro

Every 10 seconds (while a round is active):
  → Fetch full round PGN (all 16 games in one request)
  → Parse each game's moves and FEN annotations
  → For each game where move count increased:
      → Query Lichess Cloud Eval API (/api/cloud-eval?fen=...&multiPv=3)
      → Falls back to chess-api.com if position not cached
      → Compute centipawn delta → classify move
      → If blunder / mistake / brilliancy:
          → Send to Groq → Maggie Man roast commentary
          → Post Discord embed with analysis
  → When a game finishes → post result embed
```

---

## Move Classification

| Class | CP Drop (moving side) | Alerted? |
|---|---|---|
| Brilliancy | gains ≥ 150cp | ✅ Yes |
| Blunder | loses ≥ 200cp | ✅ Yes |
| Mistake | loses ≥ 100cp | ✅ Yes |
| Inaccuracy | loses ≥ 50cp | ❌ No |
| Good | < 50cp drop | ❌ No |

---

## Architecture

```
bot.py                ← Discord bot, slash commands, on_ready startup
├── monitor.py        ← Core engine: round-check loop + game poll loop
├── lichess_client.py ← Lichess API (broadcast rounds NDJSON, round PGN, cloud eval)
├── pgn_parser.py     ← Extracts games, moves, FEN annotations from PGN
├── chess_engine.py   ← Eval parsing, move classification, chess-api.com fallback
├── groq_commentary.py← Groq AI (Maggie Man personality + commentary generation)
├── embeds.py         ← Discord embed builders (move alerts, round start, reminders)
└── config.py         ← All keys and constants
```

---

## APIs Used

| API | Auth | Purpose |
|---|---|---|
| `lichess.org/api/broadcast/{id}/rounds` | None | Round list (NDJSON) |
| `lichess.org/api/broadcast/round/{id}.pgn` | None | Game PGN with FEN annotations |
| `lichess.org/api/cloud-eval` | None | Stockfish cloud eval (primary) |
| `chess-api.com/v1` | None | Stockfish REST fallback |
| Groq (`openai/gpt-oss-120b`) | API Key | Maggie Man commentary |
| Discord | Bot Token | Messages + slash commands |

---

## Bug Fixes (v2)

- **Fixed**: `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (tasks now actually start)
- **Fixed**: Broadcast rounds response parsed as NDJSON not JSON array
- **Fixed**: Round field names (`ongoing` not `started`) from Lichess API
- **Fixed**: Analysis switched from chess-api.com primary → Lichess Cloud Eval primary
- **Fixed**: PGN FEN extraction regex hardened for Lichess comment format
- **Fixed**: `classify_move()` centipawn delta direction bug
- **Added**: `diagnose.py` pre-flight check script
# Maggie-Man
