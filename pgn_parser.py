"""
PGN parser utilities.
Lichess broadcast PGNs embed FEN annotations in move comments like:
  { [%fen r1bqkbnr/pppp1ppp/.../... w KQkq - 0 1] [%clk 1:30:00] }

We extract those FENs so we never need to replay the entire move sequence.
"""

import re
import logging

logger = logging.getLogger("maggie-man.pgn")

# Matches { ... [%fen <FEN> ] ... } style Lichess comments
_FEN_RE = re.compile(r'\[%fen\s+([^\]]+)\]')
_CLK_RE = re.compile(r'\[%clk\s+([^\]]+)\]')
_HEADER_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
# Move number prefix like "1." or "1..." 
_MOVE_NUM_RE = re.compile(r'^\d+\.+$')
# Result tokens
_RESULT_RE = re.compile(r'^(1-0|0-1|1/2-1/2|\*)$')


def parse_pgn_games(pgn_text: str) -> list[dict]:
    """
    Split a multi-game PGN string and parse each game.
    Lichess separates games with a blank line before the next [Event ...] tag.
    """
    if not pgn_text or not pgn_text.strip():
        return []

    # Split on blank line followed by a tag line
    blocks = re.split(r'\n\n(?=\[)', pgn_text.strip())
    games = []
    for block in blocks:
        if not block.strip():
            continue
        g = _parse_one(block)
        if g:
            games.append(g)

    logger.debug(f"Parsed {len(games)} games from PGN")
    return games


def _parse_one(pgn: str) -> dict | None:
    """Parse a single PGN game block."""
    try:
        # ── Headers ──────────────────────────────────────────────────────────
        headers: dict[str, str] = {}
        for m in _HEADER_RE.finditer(pgn):
            headers[m.group(1)] = m.group(2)

        if not headers.get("White"):
            return None   # Incomplete game block

        # ── Move text (everything after the last header line) ─────────────
        # Remove all header lines first
        moves_section = _HEADER_RE.sub("", pgn).strip()

        # Extract FEN annotations before stripping comments
        fens = _FEN_RE.findall(moves_section)
        clks = _CLK_RE.findall(moves_section)

        # Strip { } comments entirely
        moves_section = re.sub(r'\{[^}]*\}', ' ', moves_section)
        # Strip ( ) variations
        moves_section = re.sub(r'\([^)]*\)', ' ', moves_section)
        # Strip NAG ($1, $2, ...)
        moves_section = re.sub(r'\$\d+', ' ', moves_section)

        # Collect SAN moves (skip move-number tokens and result tokens)
        tokens = moves_section.split()
        moves = []
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            if _MOVE_NUM_RE.match(tok):
                continue
            if _RESULT_RE.match(tok):
                continue
            # Basic SAN sanity: starts with a letter or O (castling)
            if re.match(r'^[a-zA-Z]|^O-O', tok):
                moves.append(tok)

        return {
            "headers": headers,
            "moves": moves,
            "fens": fens,           # list of FEN strings (one per move)
            "clks": clks,
            "white": headers.get("White", "?").strip(),
            "black": headers.get("Black", "?").strip(),
            "result": headers.get("Result", "*"),
            "round": headers.get("Round", "?"),
            "site": headers.get("Site", ""),
            "event": headers.get("Event", ""),
        }
    except Exception as e:
        logger.error(f"_parse_one error: {e}", exc_info=True)
        return None


def get_game_id(game: dict) -> str:
    """Stable unique ID for a game within a round."""
    white = game["white"].replace(" ", "_")
    black = game["black"].replace(" ", "_")
    round_ = game.get("round", "?")
    return f"{round_}::{white}::vs::{black}"


def get_latest_fen(game: dict) -> str | None:
    """Return the FEN after the most recent move, or None."""
    fens = game.get("fens", [])
    return fens[-1].strip() if fens else None


def get_move_count(game: dict) -> int:
    """Total number of half-moves (plies) played."""
    return len(game.get("moves", []))


def get_last_move_san(game: dict) -> str | None:
    moves = game.get("moves", [])
    return moves[-1] if moves else None


def is_game_over(game: dict) -> bool:
    return game.get("result", "*") in ("1-0", "0-1", "1/2-1/2")
