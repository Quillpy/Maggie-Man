import aiohttp
import asyncio
import logging

logger = logging.getLogger("maggie-man.engine")

CHESS_API_URL = "https://chess-api.com/v1"

# Move classification thresholds (centipawns = cp / 100 = pawns)
# delta = how much the moving side LOST in eval
BLUNDER_THRESHOLD  = 200   # cp drop >= 200 = blunder
MISTAKE_THRESHOLD  = 100   # cp drop >= 100 = mistake
INACCURACY_THRESHOLD = 50  # cp drop >= 50  = inaccuracy
BRILLIANCY_GAIN    = 150   # cp GAIN >= 150 for moving side = brilliancy

ALERT_CLASSIFICATIONS = {"blunder", "mistake", "brilliancy"}


def _cp_to_pawns(cp: int | float) -> float:
    return cp / 100.0


def classify_move(cp_before: float | None, cp_after: float | None,
                  turn_before: str) -> str:
    """
    Classify a move based on centipawn change.

    cp_before / cp_after: eval in PAWNS from white's POV.
    turn_before: 'w' (white just moved) or 'b' (black just moved).

    A white move is good if cp goes UP (white gains advantage).
    A black move is good if cp goes DOWN (black gains advantage).
    """
    if cp_before is None or cp_after is None:
        return "unknown"

    # Convert to moving-side delta: positive = moving side gained
    if turn_before == "w":
        delta = cp_after - cp_before        # positive = white gained (good)
    else:
        delta = cp_before - cp_after        # positive = black gained (good)

    delta_cp = delta * 100  # back to centipawns for threshold comparison

    if delta_cp <= -BLUNDER_THRESHOLD:
        return "blunder"
    elif delta_cp <= -MISTAKE_THRESHOLD:
        return "mistake"
    elif delta_cp <= -INACCURACY_THRESHOLD:
        return "inaccuracy"
    elif delta_cp >= BRILLIANCY_GAIN:
        return "brilliancy"
    else:
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
    elif pawns < -0.3:
        return "black"
    return "equal"


def parse_cloud_eval(data: dict) -> tuple[float | None, int | None, str, list[str]]:
    """
    Parse a Lichess cloud-eval response into usable values.

    Returns: (eval_pawns, mate, best_move_uci, continuation_uci_list)
    eval_pawns: white-POV pawn value (None if mate)
    mate: forced mate in N (None if not forced)
    best_move_uci: e.g. "e2e4"
    continuation: list of UCI moves for best line
    """
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
    """
    Fallback: evaluate via chess-api.com (free Stockfish REST API).
    Used when Lichess cloud eval has no cached data for the position.

    Returns: (eval_pawns, mate, best_move_san, continuation)
    """
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
                    # chess-api returns type: "bestmove" | "move" | "info"
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
        logger.error(f"chess-api.com error: {e}")
        return None, None, "?", []
