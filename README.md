# Maggie Man — Lichess Tournament Discord Bot

Advanced Discord bot for following Lichess tournaments and games. Maggie provides move alerts, game summaries, Magnus-style commentary via Groq AI.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/search <query> [page]` | Search tournaments, **Follow** buttons (server-wide tournament follow) | - |
| `/status` | Bot status, followed tournament/boards | - |
| `/pair <tid> <rnd>` | Show round pairings (board: player1 vs player2) | - |
| `/board <tid> <rnd> <board>` | View board game/stream, **Toggle follow** button (server-wide board follow) | Manage Server |

- **tid**: 8-char tournament ID (from /search footer).
- **rnd**: Round ID or name.
- **board**: Board number from /pair.

Alerts/post to `<#DISCORD_CHESS_CHANNEL_ID>` channel:
- Round reminders 1h before.
- Move highlights (blunder/mistake/inaccuracy/great/brilliant) with eval, engine line, Maggie comment.
- Game end summaries with Maggie recap.
- Tournament follow: all boards. Board follow: specific boards only.

## Features

- Server-wide tournament + per-board follows (data/\<guild_id\>/json).
- Lichess broadcast search, rounds, PGN parsing, cloud eval.
- Filter alerts by followed boards.
- Clean embeds, Magnus parody commentary (Groq).
- Tournament/round/game stream links.

## Setup (Local)

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv/Scripts/activate on Windows
pip install -r requirements.txt
cp .env.example .env  # create if missing
```

Edit `.env`:
```
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_CHESS_CHANNEL_ID=1234567890  # alerts channel ID
GROQ_API_KEY=your_groq_key
LICHESS_API_TOKEN=lichess_oauth_optional_for_eval
LICHESS_API_BASE=https://lichess.free/api
LICHESS_CLOUD_EVAL_URL=https://lichess.free/api/cloud-eval
LICHESS_SITE_BASE=https://lichess.free/broadcast
DISCORD_GUILD_ID=optional_guild_for_sync  # for /sync guild cmds
GROQ_MODEL=llama-3.1-70b-versatile
```

Run:
```bash
python -m core.bot
```

Sync cmds: `/sync` if GUILD_ID set (dev).

## Deployment (Railway)

1. [Railway.app](https://railway.app) new project → Deploy from GitHub repo.
2. Variables: Add all `.env` keys/values.
3. Railway detects Python, installs `requirements.txt`, runs `python -m core.bot`.
4. Invite bot to server, set `DISCORD_CHESS_CHANNEL_ID`.
5. Logs in Railway dashboard.

**Railway tips**:
- Add **Procfile**: `worker
- Procfile not needed (detects).
- data/ dir ephemeral; follows JSON lost on restart (add Railway volume or Redis later).
- Free tier OK for low traffic.

## Future Plans / Suggested Adds

- Per-user follows (DB).
- Live board images (chessboard.js).
- Leaderboard top blunders.
- Multi-tournament support.
- Voice TTS commentary.
- Railway Postgres for persistent follows.
- Web dashboard.
- More AI: full PGN analysis, player styles.

## Troubleshooting

- No alerts: Check channel ID, tournament follow (/status).
- Cmds missing: Invite bot w/ apps.commands, or set GUILD_ID + /sync.
- Groq errors: Check API key/model.
- PGN parse fail: Rare Lichess format.

Neat, clean, deploy-ready!

⭐ Star/fork if useful.

