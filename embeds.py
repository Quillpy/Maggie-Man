# Discord embed builders for Maggie Man bot.

from datetime import datetime, timezone

import discord

from chess_engine import format_eval, get_winning_side


CLASSIFICATION_CONFIG = {
    "blunder": {
        "emoji": "💥",
        "color": 0xFF0000,
        "label": "BLUNDER",
    },
    "mistake": {
        "emoji": "😬",
        "color": 0xFF8C00,
        "label": "MISTAKE",
    },
    "brilliancy": {
        "emoji": "✨",
        "color": 0xFFD700,
        "label": "BRILLIANCY",
    },
    "inaccuracy": {
        "emoji": "🤔",
        "color": 0xAAAAAA,
        "label": "INACCURACY",
    },
}


def build_move_embed(
    white: str,
    black: str,
    round_name: str,
    board_number: int | None,
    move_san: str,
    move_number: int,
    classification: str,
    eval_before: float,
    eval_after: float,
    mate_before: int | None,
    mate_after: int | None,
    top_move: str,
    continuation: list[str],
    commentary: str,
    lichess_url: str = "",
) -> discord.Embed:
    """Build the embed for a critical move alert."""
    cfg = CLASSIFICATION_CONFIG.get(classification, CLASSIFICATION_CONFIG["mistake"])
    
    winning = get_winning_side(eval_after, mate_after)
    eval_b_str = format_eval(eval_before, mate_before)
    eval_a_str = format_eval(eval_after, mate_after)

    title = f"{cfg['emoji']} {cfg['label']}! — {white} vs {black}"
    if board_number:
        title = f"{cfg['emoji']} {cfg['label']}! — Board {board_number}: {white} vs {black}"

    embed = discord.Embed(
        title=title,
        description=commentary,
        color=cfg["color"],
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="♟️ Move Played",
        value=f"`{move_number}. {move_san}`",
        inline=True
    )
    embed.add_field(
        name="🔄 Eval Change",
        value=f"`{eval_b_str}` → `{eval_a_str}`",
        inline=True
    )
    embed.add_field(
        name="🏆 Best Move",
        value=f"`{top_move}`",
        inline=True
    )

    if continuation:
        cont_str = " ".join(continuation[:5])
        embed.add_field(
            name="🔮 Engine Line",
            value=f"`{cont_str}`",
            inline=False
        )

    winning_emoji = {"white": "⬜ White", "black": "⬛ Black", "equal": "⚖️ Equal"}.get(winning, "⚖️ Equal")
    embed.add_field(name="📊 Position", value=winning_emoji, inline=True)
    embed.add_field(name="🎯 Round", value=round_name, inline=True)

    if lichess_url:
        embed.add_field(name="🔗 Watch Live", value=f"[Lichess]({lichess_url})", inline=True)

    embed.set_footer(text="Maggie Man • 2800+ GM • Stockfish 18 Analysis")
    return embed


def build_round_start_embed(
    round_name: str,
    pairings: list[dict],
    commentary: str,
    broadcast_url: str = "",
) -> discord.Embed:
    """Build embed for round start announcement."""
    embed = discord.Embed(
        title=f"🏁 {round_name} — STARTED!",
        description=commentary,
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )

    pairings_text = ""
    for i, p in enumerate(pairings):
        board = p.get("board", i + 1)
        pairings_text += f"**Board {board}**: {p['white']} vs {p['black']}\n"

    embed.add_field(
        name=f"📋 Pairings ({len(pairings)} games)",
        value=pairings_text or "Loading pairings...",
        inline=False
    )

    if broadcast_url:
        embed.add_field(name="📺 Watch live", value=f"[Broadcast]({broadcast_url})", inline=False)

    embed.set_footer(text="Maggie Man • Broadcast tracker")
    return embed


def build_reminder_embed(
    round_name: str,
    minutes: int,
    commentary: str,
    broadcast_url: str = "",
) -> discord.Embed:
    """Build embed for pre-round reminder."""
    embed = discord.Embed(
        title=f"⏰ {round_name} starts in {minutes} minutes!",
        description=commentary,
        color=0xFF8C00,
        timestamp=datetime.now(timezone.utc),
    )
    if broadcast_url:
        embed.add_field(
            name="📺 Broadcast",
            value=f"[Watch on Lichess]({broadcast_url})",
            inline=False,
        )
    embed.set_footer(text="Maggie Man • Don't miss it")
    return embed


def build_game_over_embed(
    white: str,
    black: str,
    result: str,
    round_name: str,
    board_number: int | None,
    total_moves: int,
) -> discord.Embed:
    """Build embed for a game ending."""
    if result == "1-0":
        winner = white
        emoji = "⬜"
    elif result == "0-1":
        winner = black
        emoji = "⬛"
    else:
        winner = "Draw"
        emoji = "🤝"

    board_str = f"Board {board_number}: " if board_number else ""
    embed = discord.Embed(
        title=f"{emoji} Game Over — {board_str}{white} vs {black}",
        description=f"**Result:** `{result}` | **Moves:** {total_moves}",
        color=0x808080,
        timestamp=datetime.now(timezone.utc),
    )
    if result != "1/2-1/2":
        embed.add_field(name="🏆 Winner", value=winner, inline=True)
    embed.add_field(name="🎯 Round", value=round_name, inline=True)
    embed.set_footer(text="Maggie Man")
    return embed
