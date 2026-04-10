# Maggie Man — Lichess Tournament Bot

Discord bot that follows one Lichess tournament per server, sends 1h reminders and move highlights (inaccuracy, mistake, blunder, great move, brilliant) in the chess channel with Maggie Man (Groq-powered Magnus parody) commentary.

## Commands

| Command | Description |
|---------|-------------|
| `/search` | Search tournaments, **Follow** button to track (Manage Server, server-wide) |
| `/status` | Status (ephemeral) |

Followed tournament saved in `data/followed.json`.

## Features

- Server-wide follow.
- 1h reminder before round starts.
- Monitors all games in live rounds.
- Lichess cloud eval for move classification:
  - Inaccuracy: ≥ 50 cp lost
  - Mistake: ≥ 100 cp lost
  - Blunder: ≥ 300 cp lost
  - Great move: ≥ 100 cp gained
  - Brilliant: ≥ 200 cp gained
- Posts embeds with eval, engine top line, Maggie commentary.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: DISCORD_BOT_TOKEN, DISCORD_CHESS_CHANNEL_ID, GROQ_API_KEY
python -m core.bot
```

## Env vars

| Var | Required |
|-----|----------|
| DISCORD_BOT_TOKEN | yes |
| DISCORD_CHESS_CHANNEL_ID | yes |
| GROQ_API_KEY | yes |
| LICHESS_API_TOKEN | opt |

## References

- [Lichess API](https://lichess.org/api#tag/broadcasts)
- [discord.py](https://discordpy.readthedocs.io/)
