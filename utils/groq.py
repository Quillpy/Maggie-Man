from __future__ import annotations

import asyncio
import logging

from groq import Groq

logger = logging.getLogger("groq")

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
    cont_str = " ".join(continuation[:4]) if continuation else "none"
    board_str = f"Board {board_number}" if board_number else ""
    prompt = f"""Round: {round_name}
{board_str}
{white} vs {black}
Move: {move_san} — {classification.upper()}
Eval: {eval_before:+.1f} → {eval_after:+.1f} ({winning_side} ahead)
Engine top: {top_move} Line: {cont_str}
Give a quick sarcastic or playful line in plain language. Mention the move and what the engine wanted."""

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
    except Exception:
        return f"{white} vs {black}: {move_san} — {classification}."

async def generate_reminder_message(
    round_name: str,
    minutes_before: int,
    groq_api_key: str,
    model: str,
    tournament_name: str = "",
) -> str:
    tour_bit = f'Broadcast "{tournament_name}" — ' if tournament_name else ""
    prompt = (
        f"{tour_bit}{round_name} starts in ~{minutes_before} minutes. "
        "This is the followed Lichess broadcast for this server. "
        "One or two short sentences, casual, tiny joke, very simple words."
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
    except Exception:
        return f"{round_name} in ~{minutes_before} min. Don't be late."

async def generate_game_summary(
    white: str,
    black: str,
    result: str,
    pgn_text: str,
    groq_api_key: str,
    model: str,
) -> str:
    prompt = f"""Game PGN: {pgn_text[:2000]}...
{white} vs {black}, final result: {result}
Give a short Maggie-style recap: key moments, funny take, winner praise. Keep it light, 2-4 sentences."""

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
            0.8,
            300,
        )
    except Exception:
        return f"Solid game {white}-{black} {result}. GG!"

