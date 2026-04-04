# Groq AI message generator — short, human, sarcastic "Maggie Man" voice.

from __future__ import annotations

import logging

from groq import Groq

from chess_engine import format_eval

logger = logging.getLogger("maggie-man.groq")

MAGGIE_MAN_SYSTEM_PROMPT = """
You are Maggie Man — a chill, sarcastic chess fan (Magnus parody). You're not a textbook.
Talk like a normal person: short sentences, dry humor, light roast. No essays.
Be a little smug and funny, never cruel about real people (race, gender, etc.). Chess trash talk only.
Skip fancy words unless they actually fit. 2–6 sentences max for move blurbs; keep round/reminders shorter.
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
Round: {round_name}
{board_str}
{white} vs {black}
Move: {move_san} — tagged as {classification.upper()}
Eval: {eval_before} -> {eval_after} ({winning_side} better)
Engine liked: {top_move}  Line: {cont_str}

Give a quick sarcastic take. Mention the move and what the engine wanted.
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
    model: str,
) -> str:
    client = Groq(api_key=groq_api_key)
    prompt = _build_move_prompt(
        white,
        black,
        round_name,
        move_san,
        classification,
        format_eval(eval_before, None),
        format_eval(eval_after, None),
        top_move,
        continuation,
        winning_side,
        board_number,
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_completion_tokens=280,
            top_p=1,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("Groq move commentary: %s", e)
        return _fallback_commentary(white, black, move_san, classification)


def _fallback_commentary(white: str, black: str, move_san: str, classification: str) -> str:
    fallbacks = {
        "blunder": f"Yikes. {white} vs {black}, {move_san} — that's a blunder. Maggie Man saw it in half a second.",
        "mistake": f"{white} vs {black}: {move_san} hurts. Not Maggie Man–approved.",
        "brilliancy": f"OK fine, {move_san} in {white} vs {black} was actually spicy. Almost respectable.",
    }
    return fallbacks.get(
        classification,
        f"{move_san} happened in {white} vs {black}. The engine has opinions.",
    )


async def generate_round_start_message(
    round_name: str,
    pairings: list[dict],
    groq_api_key: str,
    model: str,
) -> str:
    client = Groq(api_key=groq_api_key)
    pairings_text = "\n".join(
        [
            f"Board {p.get('board', i + 1)}: {p['white']} vs {p['black']}"
            for i, p in enumerate(pairings)
        ]
    )
    prompt = f"""
{round_name} is starting.

Pairings:
{pairings_text}

Two or three sentences: hyped but lazy sarcasm. Pick one matchup to poke fun at.
"""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_completion_tokens=200,
            top_p=1,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("Groq round start: %s", e)
        return f"{round_name} is live — {len(pairings)} boards. Grab popcorn; someone’s gonna walk into something."


async def generate_reminder_message(
    round_name: str,
    minutes_before: int,
    groq_api_key: str,
    model: str,
) -> str:
    client = Groq(api_key=groq_api_key)
    prompt = f"""
{round_name} starts in {minutes_before} minutes.
One or two sentences — casual reminder, tiny joke, no lecture.
"""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": MAGGIE_MAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_completion_tokens=120,
            top_p=1,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("Groq reminder: %s", e)
        return f"{round_name} in {minutes_before} minutes. Yes, you still have time to pretend you prepared."
