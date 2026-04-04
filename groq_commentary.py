
# Groq AI message generator.
# Generates Maggie Man flavoured commentary for chess events.


import logging
from groq import Groq
from chess_engine import format_eval

logger = logging.getLogger("maggie-man.groq")

MAGGIE_MAN_SYSTEM_PROMPT = """
You are Maggie Man, a hilarious parody of Magnus Carlsen — the greatest chess player who ever lived (obviously).

Your personality:
- You are a self-proclaimed 2800+ GM who thinks every other player is a hopeless amateur
- You are funny, witty, sarcastic, and roast other players constantly  
- You glorify your own chess achievements at every opportunity
- You refer to yourself as "Maggie Man" occasionally in third person
- You call mistakes "embarrassing" and blunders "absolutely criminal"
- When someone plays brilliantly you say "that's almost Maggie Man level... almost"
- You speak casually, like a streamer commentating live chess
- You use chess lingo naturally (prophylaxis, zwischenzug, zugzwang, etc.)
- You keep messages punchy and entertaining — no walls of text
- You are NOT racist, sexist, or genuinely offensive. Just chess-trash-talk

Always end messages with a short Maggie Man wisdom quote or flex.
Keep responses short in few lines.
"""


def _build_move_prompt(
    white: str,
    black: str,
    round_name: str,
    move_san: str,
    classification: str,
    eval_before: str,
    eval_after: str,
    top_move: str,
    continuation: list[str],
    winning_side: str,
    board_number: int | None,
) -> str:
    cont_str = " ".join(continuation[:4]) if continuation else "none"
    board_str = f"Board {board_number}" if board_number else ""

    return f"""
Chess event: FIDE Candidates 2026
{board_str} | {round_name}
Game: {white} vs {black}
Move played: {move_san}
Classification: {classification.upper()}
Eval before: {eval_before}
Eval after: {eval_after}
Position: {winning_side} is winning
Engine's best move was: {top_move}
Engine continuation: {cont_str}

Write a short, entertaining Maggie Man commentary about this {classification}. 
{"Roast the player who blundered/made a mistake!" if classification in ("blunder", "mistake") else "Express grudging respect but still act superior."}
Include the move played ({move_san}) and what the engine preferred ({top_move}).
"""


async def generate_move_commentary(
    white: str,
    black: str,
    round_name: str,
    move_san: str,
    classification: str,
    eval_before: float,
    eval_after: float,
    top_move: str,
    continuation: list[str],
    winning_side: str,
    board_number: int | None,
    groq_api_key: str,
) -> str:
    """Generate a Maggie Man commentary for a critical move."""
    client = Groq(api_key=groq_api_key)
    prompt = _build_move_prompt(
        white, black, round_name, move_san, classification,
        format_eval(eval_before, None), format_eval(eval_after, None),
        top_move, continuation, winning_side, board_number
    )
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
            max_completion_tokens=300,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
            stop=None
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq error generating commentary: {e}")
        return _fallback_commentary(white, black, move_san, classification)


def _fallback_commentary(white: str, black: str, move_san: str, classification: str) -> str:
    """Fallback when Groq is unavailable."""
    fallbacks = {
        "blunder": f"🤦 {white} vs {black} — {move_san} was played. An absolute BLUNDER. Maggie Man would never.",
        "mistake": f"😬 {white} vs {black} — {move_san}? That's a mistake. Clearly hasn't studied Maggie Man's games.",
        "brilliancy": f"✨ {white} vs {black} — {move_san}! That's actually impressive. Almost Maggie Man level. Almost.",
    }
    return fallbacks.get(classification, f"Move {move_san} in {white} vs {black}")


async def generate_round_start_message(
    round_name: str,
    pairings: list[dict],
    groq_api_key: str,
) -> str:
    """Generate a Maggie Man intro for a round starting."""
    client = Groq(api_key=groq_api_key)
    pairings_text = "\n".join(
        [f"Board {p.get('board', i+1)}: {p['white']} vs {p['black']}" 
         for i, p in enumerate(pairings)]
    )
    prompt = f"""
FIDE Candidates 2026 - {round_name} is starting!

Pairings:
{pairings_text}

Write a short Maggie Man intro for this round. Pick 1-2 matchups and make a prediction (or just roast everyone). 
Be funny and hype. Keep it under 120 words.
"""
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
            max_completion_tokens=250,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
            stop=None
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq round start error: {e}")
        return f"🏁 {round_name} begins! {len(pairings)} games on the board. Let's see who embarrasses themselves today."


async def generate_reminder_message(
    round_name: str,
    minutes_before: int,
    groq_api_key: str,
) -> str:
    """Generate a reminder message."""
    client = Groq(api_key=groq_api_key)
    prompt = f"""
FIDE Candidates 2026 - {round_name} starts in {minutes_before} minutes!
Write a short Maggie Man hype message reminding people to tune in.
Be funny. Under 80 words.
"""
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
            max_completion_tokens=150,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
            stop=None
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq reminder error: {e}")
        return f"⏰ **{round_name}** starts in {minutes_before} minutes! Get ready for some questionable chess."
