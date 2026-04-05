from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("maggie-man.board-follow")

_DATA_DIR = Path(__file__).resolve().parent / "data"
_FILE = _DATA_DIR / "followed_board.json"


def load_followed_board() -> int | None:
    if not _FILE.is_file():
        return None
    try:
        raw = json.loads(_FILE.read_text(encoding="utf-8"))
        n = raw.get("board_number")
        if n is None:
            return None
        i = int(n)
        return i if i > 0 else None
    except Exception as e:
        logger.warning("Could not read %s: %s", _FILE, e)
        return None


def save_followed_board(board_number: int | None) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    n = None if board_number is None or board_number <= 0 else int(board_number)
    payload = {"board_number": n}
    _FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_followed_board_file() -> None:
    try:
        if _FILE.is_file():
            _FILE.unlink()
    except OSError as e:
        logger.warning("Could not remove %s: %s", _FILE, e)
