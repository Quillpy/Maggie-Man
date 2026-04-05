from __future__ import annotations

import asyncio
import logging

from groq import Groq

from chess_engine import format_eval

logger = logging.getLogger("maggie-man.groq")

MAGGIE_MAN_SYSTEM = """
You are Maggie Man — a chill chess fan (light Magnus parody).
Write like a real person: short, simple words, easy to read. No fancy jargon unless it's chess.
Keep answers brief. Never insult real people; chess jokes are fine.
"""


def _run_groq_chat(
    groq_api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_completion_tokens: int,
) -> str:
    client = Groq(api_key=groq_api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
        top_p=1,
        stream=False,
    )
    return (completion.choices[0].message.content or "").strip()


def _move_prompt(
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
    return f"""Round: {round_name}
{board_str}
{white} vs {black}
Move: {move_san} — {classification.upper()}
Eval: {eval_before} → {eval_after} ({winning_side} ahead)
Engine top: {top_move}  Line: {cont_str}
Give a quick sarcastic or playful line in plain language. Mention the move and what the engine wanted."""


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
    prompt = _move_prompt(
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
    messages = [
        {"role": "system", "content": MAGGIE_MAN_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        return await asyncio.to_thread(
            _run_groq_chat,
            groq_api_key,
            model,
            messages,
            0.9,
            280,
        )
    except Exception as e:
        logger.error("Groq move: %s", e)
        return _fallback(white, black, move_san, classification)


def _fallback(white: str, black: str, move_san: str, classification: str) -> str:
    return {
        "blunder": f"{white} vs {black}: {move_san} — big slip.",
        "mistake": f"{white} vs {black}: {move_san} — ouch.",
        "inaccuracy": f"{white} vs {black}: {move_san} — a bit loose.",
        "brilliancy": f"{white} vs {black}: {move_san} — nice one.",
        "great_move": f"{white} vs {black}: {move_san} — solid.",
        "good": f"{white} vs {black}: {move_san} — game goes on.",
    }.get(classification, f"{move_san} in {white} vs {black}.")


async def generate_reminder_message(
    round_name: str,
    minutes_before: int,
    groq_api_key: str,
    model: str,
    *,
    tournament_name: str = "",
    pairings_excerpt: str = "",
) -> str:
    tour_bit = f'Broadcast "{tournament_name}" — ' if tournament_name else ""
    pair_bit = ""
    if pairings_excerpt.strip():
        pair_bit = (
            "\n\nPairings (excerpt for tone only; full list is in the message):\n"
            f"{pairings_excerpt[:1200]}"
        )
    prompt = (
        f"{tour_bit}{round_name} starts in ~{minutes_before} minutes. "
        "This is the **followed** Lichess broadcast for this server. "
        "One or two short sentences, casual, tiny joke, very simple words."
        f"{pair_bit}"
    )
    messages = [
        {"role": "system", "content": MAGGIE_MAN_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        return await asyncio.to_thread(
            _run_groq_chat,
            groq_api_key,
            model,
            messages,
            0.9,
            180,
        )
    except Exception as e:
        logger.error("Groq reminder: %s", e)
        return f"{round_name} in ~{minutes_before} min. Don't be late."


async def generate_ask_reply(question: str, groq_api_key: str, model: str) -> str:
    messages = [
        {"role": "system", "content": MAGGIE_MAN_SYSTEM},
        {
            "role": "user",
            "content": (
                "They asked you something (chess or whatever fits your vibe). "
                "Answer in plain, friendly language. Stay short — a few sentences max.\n\n"
                f"Question: {question.strip()}"
            ),
        },
    ]
    try:
        return await asyncio.to_thread(
            _run_groq_chat,
            groq_api_key,
            model,
            messages,
            0.85,
            400,
        )
    except Exception as e:
        logger.error("Groq ask: %s", e)
        return "Brain fog on my end — try again in a bit."


async def generate_follow_board_commentary(
    white: str,
    black: str,
    round_name: str,
    move_san: str,
    move_number: int,
    classification: str,
    eval_before: str,
    eval_after: str,
    top_move: str,
    continuation: list[str],
    winning_side: str,
    board_number: int | None,
    engine_summary: str,
    groq_api_key: str,
    model: str,
) -> str:
    cont_str = " ".join(continuation[:6]) if continuation else "none"
    board_str = f"Board {board_number}" if board_number else ""
    prompt = f"""Live broadcast — following every move on this board.
Round: {round_name}
{board_str}
{white} vs {black}
Last move: {move_number}. {move_san}
Tag (from our eval): {classification.upper()}
Eval before → after: {eval_before} → {eval_after} ({winning_side} looks better)
Engine first move: {top_move}
Short line: {cont_str}

Lichess cloud engine (multi-PV summary):
{engine_summary}

Write Maggie Man's quick live note: simple words, human tone, 2–5 sentences. Cover the move and what the engine thinks — no bullet lists."""
    messages = [
        {"role": "system", "content": MAGGIE_MAN_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        return await asyncio.to_thread(
            _run_groq_chat,
            groq_api_key,
            model,
            messages,
            0.85,
            350,
        )
    except Exception as e:
        logger.error("Groq follow-board: %s", e)
        return _fallback(white, black, move_san, classification)
