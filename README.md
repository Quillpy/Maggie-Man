# Maggie Man — Lichess tournament bot

Discord bot that follows **one** Lichess broadcast per server, posts reminders and engine-tagged move highlights in a single channel, with short “Maggie Man” blurbs from [Groq](https://groq.com/).

## Commands

| Command | Description |
|--------|-------------|
| `/search` | Search Lichess broadcasts. Use **Follow** on a result to set the tournament for the **whole server** (requires **Manage Server**). |
| `/status` | Monitor status (ephemeral). |

Followed tournament id and URL are stored in `data/followed_broadcast.json` (created on first follow). After a bot restart, run `/search` again if **Follow** buttons on an old message stop working; the saved tournament still applies.

## Chess channel behavior

When a broadcast is followed, the bot posts in `DISCORD_CHESS_CHANNEL_ID`:

1. **Reminder** when a round’s `startsAt` is within `REMINDER_MINUTES_BEFORE` (default 60 minutes).
2. **Move alerts** when a new move is classified from eval swing (Lichess cloud eval, then `chess-api.com` if needed), using centipawns from the moving side’s perspective:
   - Inaccuracy: ≥ 50 cp lost  
   - Mistake: ≥ 100 cp lost  
   - Blunder: ≥ 300 cp lost  
   - Great move: ≥ 100 cp gained  
   - Brilliant: ≥ 200 cp gained  

Each alert sends context to Groq and posts the reply in Discord.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — DISCORD_BOT_TOKEN, DISCORD_CHESS_CHANNEL_ID, GROQ_API_KEY
python bot.py
```

Enable the **Message Content Intent** for the bot if you rely on message content elsewhere (slash commands work without it).

## Env vars

| Variable | Required | Notes |
|----------|----------|--------|
| `DISCORD_BOT_TOKEN` | yes | |
| `DISCORD_CHESS_CHANNEL_ID` | yes | Channel for reminders and move posts |
| `GROQ_API_KEY` | yes | |
| `GROQ_MODEL` | no | Default `openai/gpt-oss-120b` |
| `LICHESS_API_BASE` / `LICHESS_SITE_BASE` | no | Defaults `https://lichess.org/api` and `https://lichess.org` |
| `LICHESS_API_TOKEN` | no | OAuth bearer | Optional 
| `POLL_INTERVAL_SECONDS` | no | Default `10` |
| `REMINDER_MINUTES_BEFORE` | no | Default `60` |
| `ROUND_CHECK_INTERVAL_SECONDS` | no | Default `120` |

## Railway

`railway.json` runs `python bot.py`. Set the same env vars as in `.env`. Use **one** replica.

## References

- [Lichess Broadcast API](https://lichess.org/api#tag/broadcasts)
- [discord.py](https://discordpy.readthedocs.io/)
