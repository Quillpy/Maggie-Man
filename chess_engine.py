import asyncio
import logging

import aiohttp

logger = logging.getLogger("maggie-man.engine")

CHESS_API_URL = "https://chess-api.com/v1"

BLUNDER_CP = 300
MISTAKE_CP = 100
INACCURACY_CP = 50
BRILLIANT_GAIN_CP = 200
GREAT_MOVE_GAIN_CP = 100

ALERT_CLASSIFICATIONS = frozenset(
    {"blunder", "mistake", "inaccuracy", "brilliancy", "great_move"}
)


def _cp_to_pawns(cp: int | float) -> float:
    return cp / 100.0


def classify_move(
    cp_before: float | None,
    cp_after: float | None,
    turn_before: str,
) -> str:
    if cp_after is None:
        return "good"
    before = 0.0 if cp_before is None else cp_before

    if turn_before == "w":
        delta = cp_after - before
    else:
        delta = before - cp_after

    delta_cp = delta * 100

    if delta_cp <= -BLUNDER_CP:
        return "blunder"
    if delta_cp <= -MISTAKE_CP:
        return "mistake"
    if delta_cp <= -INACCURACY_CP:
        return "inaccuracy"
    if delta_cp >= BRILLIANT_GAIN_CP:
        return "brilliancy"
    if delta_cp >= GREAT_MOVE_GAIN_CP:
        return "great_move"
    return "good"


def is_alert_worthy(classification: str) -> bool:
    return classification in ALERT_CLASSIFICATIONS


def format_eval(pawns: float | None, mate: int | None) -> str:
    if mate is not None:
        sign = "+" if mate > 0 else ""
        return f"M{sign}{mate}"
    if pawns is None:
        return "?"
    sign = "+" if pawns >= 0 else ""
    return f"{sign}{pawns:.2f}"


def get_winning_side(pawns: float | None, mate: int | None) -> str:
    if mate is not None:
        return "white" if mate > 0 else "black"
    if pawns is None:
        return "equal"
    if pawns > 0.3:
        return "white"
    if pawns < -0.3:
        return "black"
    return "equal"


def summarize_cloud_eval_for_prompt(data: dict | None) -> str:
    """Compact text of Lichess cloud-eval JSON for LLM context."""
    if not data:
        return "No Lichess cloud-eval (used fallback engine if any)."
    pvs = data.get("pvs") or []
    if not pvs:
        return "Cloud-eval returned no principal variations."
    lines: list[str] = []
    for i, pv in enumerate(pvs[:3], start=1):
        cp = pv.get("cp")
        mate = pv.get("mate")
        moves = (pv.get("moves") or "").split()
        head = " ".join(moves[:12]) if moves else "(no moves)"
        if mate is not None:
            ev = f"mate in {mate}"
        elif cp is not None:
            ev = f"{cp / 100.0:+.2f} pawns"
        else:
            ev = "?"
        lines.append(f"Line {i} ({ev}): {head}")
    return "\n".join(lines)


def parse_cloud_eval(data: dict) -> tuple[float | None, int | None, str, list[str]]:
    pvs = data.get("pvs", [])
    if not pvs:
        return None, None, "?", []

    best_pv = pvs[0]
    moves_str = best_pv.get("moves", "")
    moves_list = moves_str.split() if moves_str else []
    best_move = moves_list[0] if moves_list else "?"

    cp = best_pv.get("cp")
    mate = best_pv.get("mate")

    eval_pawns = _cp_to_pawns(cp) if cp is not None else None

    return eval_pawns, mate, best_move, moves_list


async def evaluate_with_chess_api(fen: str) -> tuple[float | None, int | None, str, list[str]]:
    payload = {
        "fen": fen,
        "depth": 15,
        "variants": 1,
        "maxThinkingTime": 80,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CHESS_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    ev = d.get("eval")
                    mate = d.get("mate")
                    san = d.get("san") or d.get("move", "?")
                    cont = d.get("continuationArr", [])
                    pawns = ev if ev is not None else None
                    return pawns, mate, san, cont
                return None, None, "?", []
    except asyncio.TimeoutError:
        logger.warning("chess-api.com: timed out")
        return None, None, "?", []
    except Exception as e:
        logger.error("chess-api.com error: %s", e)
        return None, None, "?", []
