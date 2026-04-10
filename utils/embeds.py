from datetime import datetime, timezone

import discord

from utils.engine import format_eval, get_winning_side

CLASSIFICATION_CONFIG = {
    "blunder": {"emoji": "💥", "color": 0xFF0000, "label": "BLUNDER"},
    "mistake": {"emoji": "😬", "color": 0xFF8C00, "label": "MISTAKE"},
    "inaccuracy": {"emoji": "🤔", "color": 0xAAAAAA, "label": "INACCURACY"},
    "great_move": {"emoji": "👍", "color": 0x57F287, "label": "GREAT MOVE"},
    "brilliant": {"emoji": "✨", "color": 0xFFD700, "label": "BRILLIANT"},
    "good": {"emoji": "♟️", "color": 0x5865F2, "label": "MOVE"},
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
    cfg = CLASSIFICATION_CONFIG.get(classification, CLASSIFICATION_CONFIG["good"])

    winning = get_winning_side(eval_after, mate_after)
    eval_b_str = format_eval(eval_before, mate_before)
    eval_a_str = format_eval(eval_after, mate_after)

    title = f"{cfg['emoji']} {cfg['label']} — {white} vs {black}"
    if board_number:
        title = f"{cfg['emoji']} {cfg['label']} — Board {board_number}: {white} vs {black}"

    embed = discord.Embed(
        title=title,
        description=commentary,
        color=cfg["color"],
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="Move", value=f"`{move_number}. {move_san}`", inline=True)
    embed.add_field(name="Eval", value=f"`{eval_b_str}` → `{eval_a_str}`", inline=True)
    embed.add_field(name="Engine", value=f"`{top_move}`", inline=True)

    if continuation:
        cont_str = " ".join(continuation[:5])
        embed.add_field(name="Line", value=f"`{cont_str}`", inline=False)

    pos = {"white": "White", "black": "Black", "equal": "Equal"}.get(winning, "Equal")
    embed.add_field(name="Position", value=pos, inline=True)
    embed.add_field(name="Round", value=round_name, inline=True)

    if lichess_url:
        embed.add_field(name="Watch", value=f"[Lichess]({lichess_url})", inline=True)

    embed.set_footer(text="Maggie Man")
    return embed

def build_reminder_embed(
    round_name: str,
    minutes: int,
    commentary: str,
    broadcast_url: str = "",
    tournament_name: str = "",
    round_url: str = "",
    pairings_text: str = "",
) -> discord.Embed:
    tname = tournament_name.strip() or "Followed broadcast"
    desc = f"**{round_name}** starts in ~**{minutes}** min.\n\n{commentary}"
    if len(desc) > 4096:
        desc = desc[:4093] + "…"
    embed = discord.Embed(
        title=f"⏰ Followed: {tname}",
        description=desc,
        color=0xFF8C00,
        timestamp=datetime.now(timezone.utc),
    )
    links: list[str] = []
    if broadcast_url:
        links.append(f"[Tournament]({broadcast_url})")
    if round_url:
        links.append(f"[This round]({round_url})")
    if links:
        embed.add_field(name="Links", value=" · ".join(links), inline=False)
    if pairings_text.strip():
        pt = pairings_text.strip()
        embed.add_field(
            name="Pairings",
            value=pt[:1020] + ("…" if len(pt) > 1020 else ""),
            inline=False,
        )
    embed.set_footer(text="Maggie Man · followed tournament reminder")
    return embed

def build_pairings_embed(round_name: str, pairings: list[dict], tid: str = "") -> discord.Embed:
    embed = discord.Embed(title=f"{round_name} - Pairings", color=0x5865F2)
    for p in pairings:
        name = f"Board {p['board']}"
        value = f"{p['white']} vs {p['black']}"
        embed.add_field(name=name, value=value, inline=True)
    if tid:
        embed.set_footer(text=f"Tournament: {tid}")
    return embed

def build_game_end_embed(
    white: str,
    black: str,
    result: str,
    summary: str,
    board_number: int | None,
    round_name: str,
    game_url: str,
) -> discord.Embed:
    title = f"🏁 Game End"
    if board_number:
        title += f" - Board {board_number}"
    embed = discord.Embed(title=title, description=summary, color=0x00AA00, url=game_url)
    embed.add_field(name=f"Result", value=result, inline=True)
    embed.add_field(name="Players", value=f"{white} vs {black}", inline=True)
    embed.add_field(name="Round", value=round_name, inline=True)
    embed.set_footer(text="Maggie Man")
    return embed

