import logging
import re

logger = logging.getLogger("maggie-man.pgn")

_FEN_RE = re.compile(r"\[%fen\s+([^\]]+)\]")
_HEADER_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
_MOVE_NUM_RE = re.compile(r"^\d+\.+$")
_RESULT_RE = re.compile(r"^(1-0|0-1|1/2-1/2|\*)$")


def parse_pgn_games(pgn_text: str) -> list[dict]:
    if not pgn_text or not pgn_text.strip():
        return []

    blocks = re.split(r"\n\n(?=\[)", pgn_text.strip())
    games = []
    for block in blocks:
        if not block.strip():
            continue
        g = _parse_one(block)
        if g:
            games.append(g)

    logger.debug("Parsed %s games", len(games))
    return games


def _parse_one(pgn: str) -> dict | None:
    try:
        headers: dict[str, str] = {}
        for m in _HEADER_RE.finditer(pgn):
            headers[m.group(1)] = m.group(2)

        if not headers.get("White"):
            return None

        moves_section = _HEADER_RE.sub("", pgn).strip()

        fens = _FEN_RE.findall(moves_section)

        moves_section = re.sub(r"\{[^}]*\}", " ", moves_section)
        moves_section = re.sub(r"\([^)]*\)", " ", moves_section)
        moves_section = re.sub(r"\$\d+", " ", moves_section)

        moves = []
        for tok in moves_section.split():
            tok = tok.strip()
            if not tok or _MOVE_NUM_RE.match(tok) or _RESULT_RE.match(tok):
                continue
            if re.match(r"^[a-zA-Z]|^O-O", tok):
                moves.append(tok)

        return {
            "headers": headers,
            "moves": moves,
            "fens": fens,
            "clks": [],
            "raw_pgn": pgn.strip(),
            "white": headers.get("White", "?").strip(),
            "black": headers.get("Black", "?").strip(),
            "result": headers.get("Result", "*"),
            "round": headers.get("Round", "?"),
            "site": headers.get("Site", ""),
            "event": headers.get("Event", ""),
        }
    except Exception as e:
        logger.error("_parse_one: %s", e, exc_info=True)
        return None


def get_game_id(game: dict) -> str:
    white = game["white"].replace(" ", "_")
    black = game["black"].replace(" ", "_")
    round_ = game.get("round", "?")
    return f"{round_}::{white}::vs::{black}"


def get_latest_fen(game: dict) -> str | None:
    fens = game.get("fens", [])
    return fens[-1].strip() if fens else None


def get_move_count(game: dict) -> int:
    return len(game.get("moves", []))


def get_last_move_san(game: dict) -> str | None:
    moves = game.get("moves", [])
    return moves[-1] if moves else None


def is_game_over(game: dict) -> bool:
    return game.get("result", "*") in ("1-0", "0-1", "1/2-1/2")
