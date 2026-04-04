import os

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "Your Discord Bot Token Here")
DISCORD_CHESS_CHANNEL_ID = int(os.getenv("DISCORD_CHESS_CHANNEL_ID", "Channel ID where bot will send messages"))

# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "Your Groq API Key Here")

# Lichess Candidates 2026 Broadcast
CANDIDATES_BROADCAST_ID = "OqKQ3sJH"
CANDIDATES_BROADCAST_SLUG = "fide-candidates-2026--combined-open--women"

# Lichess API base
LICHESS_API_BASE = "https://lichess.org/api"

# Lichess Cloud Eval (analysis API)
# GET /api/cloud-eval?fen=<fen>&multiPv=<n>
LICHESS_CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"

# Monitoring
POLL_INTERVAL_SECONDS = 10    # Poll every 10s for classical games
REMINDER_MINUTES_BEFORE = 60  # Send reminder 60min before round
