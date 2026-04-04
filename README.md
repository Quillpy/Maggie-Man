# Maggie Man — Discord chess broadcast bot

Python bot that watches a [Lichess](https://lichess.org) **broadcast tournament**, posts round reminders and start announcements in a Discord channel, and calls out big swings (blunders / mistakes / brilliancies) with short AI blurbs via [Groq](https://groq.com/). It also exposes slash commands that wrap the public **Lichess Broadcasts** HTTP API ([docs](https://lichess.org/api#tag/broadcasts)).

There is **no follow/unfollow** flow: everyone sees updates in the configured channel automatically.

## Features

- **Automatic channel updates** for one configured broadcast: pre-round reminders, round start + pairings, move alerts, game over.
- **`/lichess search`** — uses [`GET /api/broadcast/search`](https://lichess.org/api#tag/broadcasts/GET/api/broadcast/search) (time control, dates, links come from Lichess `tour.info` / `dates`).
- **Slash helpers** for the other read-only broadcast endpoints (tournament JSON, round JSON, top feed, official feed, players, team standings, PGN export URLs, optional OAuth “my rounds”).
- **`/maggie`** — casual, sarcastic chat via Groq (same API key as commentary).
- **Configuration** via `.env` (no `config.py`).

## Requirements

- Python **3.10+** (tested with 3.10–3.12+).
- A [Discord application + bot](https://discord.com/developers/applications) with the **Message Content Intent** enabled (used for prefix commands if you add them later; slash commands work regardless).
- [Groq API key](https://console.groq.com/).
- Bot **Send Messages** and **Embed Links** in the target channel.

## Local setup

1. Clone the repo and create a virtualenv (optional but recommended).

   ```bash
   cd Python-Bot
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in values (see table below).

3. Sanity-check APIs (optional):

   ```bash
   python diagnose.py
   ```

4. Run the bot:

   ```bash
   python bot.py
   ```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | yes | Bot token from the Discord Developer Portal. |
| `DISCORD_CHESS_CHANNEL_ID` | yes | Numeric ID of the text channel for tournament posts. |
| `GROQ_API_KEY` | yes | Groq API key. |
| `GROQ_MODEL` | no | Chat model id (default `openai/gpt-oss-120b`). |
| `MONITORED_BROADCAST_ID` | no | 8-character Lichess **broadcast tournament** id to watch (default: FIDE Candidates combined example). |
| `MONITORED_BROADCAST_URL` | no | Public Lichess URL for that broadcast (used in embeds). |
| `LICHESS_API_BASE` | no | Default `https://lichess.org/api`. |
| `LICHESS_SITE_BASE` | no | Default `https://lichess.org` (for `/broadcast/.../players` paths). |
| `LICHESS_API_TOKEN` | no | OAuth bearer with `study:read` for `/lichess my_rounds` and richer private data on `/lichess by_user`. |
| `POLL_INTERVAL_SECONDS` | no | How often to poll the active round PGN (default `10`). |
| `REMINDER_MINUTES_BEFORE` | no | Send a reminder when the round starts within this many minutes (default `60`). |
| `ROUND_CHECK_INTERVAL_SECONDS` | no | How often to refresh the rounds list (default `120`). |

**Security:** never commit `.env` or paste tokens into code. If tokens were ever committed, **rotate them** in Discord and Groq.

## Slash commands

| Command | Purpose |
|---------|---------|
| `/status` | Monitor stats (broadcast id, active round, move count). |
| `/maggie` | Ask the bot something (short, sarcastic replies). |
| `/lichess search` | Search broadcasts by text (`q`, `page`). |
| `/lichess tournament` | `GET /api/broadcast/{id}` — full tournament + rounds. |
| `/lichess top` | `GET /api/broadcast/top` — page 1 = active list; page 2+ uses the paginated `past` object. |
| `/lichess official` | `GET /api/broadcast?nb=…` — official NDJSON feed (first N tournaments). |
| `/lichess round` | `GET /api/broadcast/-/-/{roundId}` — round JSON + games. |
| `/lichess players` | `GET /broadcast/{id}/players` |
| `/lichess player` | `GET /broadcast/{id}/players/{playerId}` |
| `/lichess standings` | `GET /broadcast/{id}/teams/standings` |
| `/lichess by_user` | `GET /api/broadcast/by/{username}` |
| `/lichess pgn` | Prints URLs for `GET /api/broadcast/round/{id}.pgn`, `GET /api/stream/broadcast/round/{id}.pgn`, and/or `GET /api/broadcast/{id}.pgn`. |
| `/lichess my_rounds` | `GET /api/broadcast/my-rounds` (needs `LICHESS_API_TOKEN`, ephemeral). |

The client also implements `stream_round_pgn_lines()` for live PGN streaming; the bot does not keep a permanent stream open (use the URL from `/lichess pgn` or integrate yourself).

## Deploy on Railway

Railway runs a **long-lived process** (no HTTP port required for a Discord bot).

1. Push this repo to GitHub (or connect the folder) and create a **New Project** → **Deploy from GitHub** (or CLI).

2. Set **Variables** in the Railway service to match your `.env` (at minimum `DISCORD_BOT_TOKEN`, `DISCORD_CHESS_CHANNEL_ID`, `GROQ_API_KEY`).

3. **Start command:** `python bot.py`  
   The included `railway.json` sets this for Nixpacks. Railway will detect Python, install `requirements.txt`, and run the start command.

4. **Scaling:** use **one** replica. Two processes with the same bot token will fight for the connection.

5. **Logs:** open the **Deployments → View logs** tab; Python logs show sync errors, Lichess HTTP issues, and Groq failures.

6. **Free tier / sleep:** if the host sleeps, the bot goes offline until the process restarts. Use a paid/worker-friendly plan if you need always-on.

### Optional: Dockerfile

If you prefer Docker instead of Nixpacks, you can add your own `Dockerfile` that copies the project, runs `pip install -r requirements.txt`, and sets `CMD ["python", "bot.py"]`. The repo ships Nixpacks + `railway.json` only.

## How monitoring works

1. Every `ROUND_CHECK_INTERVAL_SECONDS`, the bot loads `GET /api/broadcast/{MONITORED_BROADCAST_ID}` and inspects each round’s `startsAt`, `ongoing`, and `finished` flags.
2. When a round goes live, it downloads `GET /api/broadcast/round/{roundId}.pgn`, parses games (Lichess embeds `[%fen …]` comments), and tracks new moves.
3. Evaluations use Lichess **cloud eval** when cached, otherwise a fallback HTTP engine (`chess_engine.py`).
4. Notable classifications trigger Groq commentary and a Discord embed.

## References

- [Lichess API — Broadcasts](https://lichess.org/api#tag/broadcasts)
- [Broadcast search](https://lichess.org/api#tag/broadcasts/GET/api/broadcast/search)
- [Discord.py documentation](https://discordpy.readthedocs.io/)

## License

Follow the license of the upstream repository you received this code in (add a `LICENSE` file if none exists).
