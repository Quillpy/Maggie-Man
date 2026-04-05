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


DISCORD_BOT_TOKEN = _require("DISCORD_BOT_TOKEN")
DISCORD_CHESS_CHANNEL_ID = int(_require("DISCORD_CHESS_CHANNEL_ID"))

GROQ_API_KEY = _require("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

LICHESS_API_BASE = os.getenv("LICHESS_API_BASE", "https://lichess.org/api").rstrip("/")
LICHESS_SITE_BASE = os.getenv("LICHESS_SITE_BASE", "https://lichess.org").rstrip("/")
LICHESS_CLOUD_EVAL_URL = f"{LICHESS_API_BASE}/cloud-eval"
LICHESS_API_TOKEN = os.getenv("LICHESS_API_TOKEN", "").strip() or None

POLL_INTERVAL_SECONDS = _optional_int("POLL_INTERVAL_SECONDS", 10)
REMINDER_MINUTES_BEFORE = _optional_int("REMINDER_MINUTES_BEFORE", 60)
ROUND_CHECK_INTERVAL_SECONDS = _optional_int("ROUND_CHECK_INTERVAL_SECONDS", 120)
