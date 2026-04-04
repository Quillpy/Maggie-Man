"""
Environment configuration via python-dotenv.
Copy .env.example to .env and fill in values (never commit .env).
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    v = os.getenv(name)
    if not v or not str(v).strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and set it."
        )
    return str(v).strip()


def _optional_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


# Discord
DISCORD_BOT_TOKEN = _require("DISCORD_BOT_TOKEN")
DISCORD_CHESS_CHANNEL_ID = int(_require("DISCORD_CHESS_CHANNEL_ID"))

# Groq
GROQ_API_KEY = _require("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

# Lichess — tournament this bot watches and posts updates for (8-char broadcast ID)
MONITORED_BROADCAST_ID = os.getenv("MONITORED_BROADCAST_ID", "OqKQ3sJH").strip()
MONITORED_BROADCAST_URL = os.getenv(
    "MONITORED_BROADCAST_URL",
    "https://lichess.org/broadcast/fide-candidates-2026--combined-open--women/OqKQ3sJH",
).strip()

LICHESS_API_BASE = os.getenv("LICHESS_API_BASE", "https://lichess.org/api").rstrip("/")
LICHESS_SITE_BASE = os.getenv("LICHESS_SITE_BASE", "https://lichess.org").rstrip("/")
LICHESS_CLOUD_EVAL_URL = f"{LICHESS_API_BASE}/cloud-eval"

# Optional: OAuth bearer for /api/broadcast/my-rounds and private /by/{user} data
LICHESS_API_TOKEN = os.getenv("LICHESS_API_TOKEN", "").strip() or None

# Monitor tuning
POLL_INTERVAL_SECONDS = _optional_int("POLL_INTERVAL_SECONDS", 10)
REMINDER_MINUTES_BEFORE = _optional_int("REMINDER_MINUTES_BEFORE", 60)
ROUND_CHECK_INTERVAL_SECONDS = _optional_int("ROUND_CHECK_INTERVAL_SECONDS", 120)
