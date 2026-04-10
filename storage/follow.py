import json
from pathlib import Path
from typing import Dict, Optional, Union

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def ensure_guild_dir(guild_id: int):
    path = _DATA_DIR / str(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    return path

def load_followed_tournament(guild_id: int) -> tuple[Optional[str], Optional[str]]:
    path = ensure_guild_dir(guild_id) / "followed_tournament.json"
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        bid = (raw.get("broadcast_id") or "").strip() or None
        url = (raw.get("broadcast_url") or "").strip() or None
        return bid, url
    except:
        return None, None

def save_followed_tournament(guild_id: int, broadcast_id: str, broadcast_url: str):
    path = ensure_guild_dir(guild_id)
    payload = {
        "broadcast_id": broadcast_id.strip(),
        "broadcast_url": broadcast_url.strip(),
    }
    (path / "followed_tournament.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def load_followed_boards(guild_id: int) -> Dict[str, Dict[str, set[int]]]:
    path = ensure_guild_dir(guild_id) / "followed_boards.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        boards = {}
        for tid, rounds in raw.items():
            boards[tid] = {}
            for rid, bset in rounds.items():
                boards[tid][rid] = set(bset)
        return boards
    except:
        return {}

def save_followed_boards(guild_id: int, boards: Dict[str, Dict[str, set[int]]]):
    path = ensure_guild_dir(guild_id)
    serial = {}
    for tid, rounds in boards.items():
        serial[tid] = {}
        for rid, bset in rounds.items():
            serial[tid][rid] = list(bset)
    (path / "followed_boards.json").write_text(json.dumps(serial, indent=2), encoding="utf-8")

def clear_followed_tournament(guild_id: int):
    path = ensure_guild_dir(guild_id) / "followed_tournament.json"
    try:
        if path.is_file():
            path.unlink()
    except:
        pass

def clear_followed_boards(guild_id: int):
    path = ensure_guild_dir(guild_id) / "followed_boards.json"
    try:
        if path.is_file():
            path.unlink()
    except:
        pass

