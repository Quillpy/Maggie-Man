from __future__ import annotations

import re

from pgn_parser import parse_pgn_games


def sort_broadcast_rounds(rounds: list[dict]) -> list[dict]:
    """Stable chronological order (startsAt, then createdAt)."""

    def key(r: dict) -> tuple:
        sa = r.get("startsAt")
        ca = r.get("createdAt") or 0
        if sa is not None:
            return (0, int(sa), int(ca))
        return (1, int(ca), 0)

    return sorted(rounds, key=key)


def board_sort_key(game: dict) -> tuple:
    h = game.get("headers") or {}
    raw = h.get("Board", "")
    try:
        return (0, int(str(raw).strip()))
    except (ValueError, TypeError):
        return (1, str(raw))


def games_sorted_by_board(games: list[dict]) -> list[dict]:
    return sorted(games, key=board_sort_key)


def format_pairings_lines(games: list[dict]) -> list[str]:
    lines: list[str] = []
    for g in games_sorted_by_board(games):
        h = g.get("headers") or {}
        board = h.get("Board", "").strip() or "—"
        w = g.get("white", "?")
        b = g.get("black", "?")
        lines.append(f"Board **{board}**: {w} vs {b}")
    return lines


def format_pairings_text(games: list[dict], *, max_lines: int | None = None) -> str:
    lines = format_pairings_lines(games)
    if max_lines is not None:
        lines = lines[:max_lines]
    if not lines:
        return ""
    return "\n".join(lines)


def pairings_from_pgn(pgn_text: str | None) -> tuple[list[dict], str]:
    """Returns (games, error_or_empty_message)."""
    if not pgn_text or not pgn_text.strip():
        return [], "No PGN for this round yet."
    games = parse_pgn_games(pgn_text)
    if not games:
        return [], "PGN has no games / pairings yet."
    return games, ""


_TOURNAMENT_ID_RE = re.compile(r"^[A-Za-z0-9]{8}$")


def is_valid_broadcast_tournament_id(tid: str) -> bool:
    return bool(tid and _TOURNAMENT_ID_RE.match(tid.strip()))


def pick_round_by_index(rounds_sorted: list[dict], one_based_index: int) -> dict | None:
    if one_based_index < 1 or one_based_index > len(rounds_sorted):
        return None
    return rounds_sorted[one_based_index - 1]
