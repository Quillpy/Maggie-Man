import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_followed(guild_id: int) -> tuple[str | None, str | None]:
    path = _DATA_DIR / str(guild_id) / "followed.json"
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        bid = (raw.get("broadcast_id") or "").strip() or None
        url = (raw.get("broadcast_url") or "").strip() or None
        return bid, url
    except:
        return None, None

def save_followed(guild_id: int, broadcast_id: str, broadcast_url: str) -> None:
    path = _DATA_DIR / str(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "broadcast_id": broadcast_id.strip(),
        "broadcast_url": broadcast_url.strip(),
    }
    (path / "followed.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def clear_followed(guild_id: int) -> None:
    path = _DATA_DIR / str(guild_id) / "followed.json"
    try:
        if path.is_file():
            path.unlink()
    except:
        pass
