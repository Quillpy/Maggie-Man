from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("maggie-man.storage")

_DATA_DIR = Path(__file__).resolve().parent / "data"
_FILE = _DATA_DIR / "followed_broadcast.json"


def load_followed() -> tuple[str | None, str | None]:
    if not _FILE.is_file():
        return None, None
    try:
        raw = json.loads(_FILE.read_text(encoding="utf-8"))
        bid = (raw.get("broadcast_id") or "").strip() or None
        url = (raw.get("broadcast_url") or "").strip() or None
        return bid, url
    except Exception as e:
        logger.warning("Could not read %s: %s", _FILE, e)
        return None, None


def save_followed(broadcast_id: str, broadcast_url: str) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "broadcast_id": broadcast_id.strip(),
        "broadcast_url": (broadcast_url or "").strip(),
    }
    _FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_followed() -> None:
    try:
        if _FILE.is_file():
            _FILE.unlink()
    except OSError as e:
        logger.warning("Could not remove %s: %s", _FILE, e)
