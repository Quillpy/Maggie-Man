from __future__ import annotations

import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

import follow_storage
import settings
from broadcast_ui import embed_from_full_tournament, embed_from_search_hit
from pairings import (
    format_pairings_text,
    is_valid_broadcast_tournament_id,
    pairings_from_pgn,
    pick_round_by_index,
    sort_broadcast_rounds,
)
from groq_commentary import generate_ask_reply
from lichess_client import LichessClient
from monitor import TournamentMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("maggie-man")

intents = discord.Intents.default()
intents.message_content = True

FOLLOW_PREFIX = "fm:follow:"


class MaggieBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.monitor: TournamentMonitor | None = None
        self.lichess: LichessClient | None = None
        self._setup_done: bool = False

    async def close(self) -> None:
        if self.monitor:
            self.monitor.stop()
            self.monitor = None
        if self.lichess:
            await self.lichess.close()
            self.lichess = None
        await super().close()


bot = MaggieBot()


def _button_label(name: str) -> str:
    base = f"Follow · {name}".strip()
    return base[:80] if len(base) <= 80 else base[:76] + "…"


async def _process_follow(interaction: discord.Interaction, tournament_id: str) -> None:
    tid = tournament_id.strip()
    if not is_valid_broadcast_tournament_id(tid):
        await interaction.response.send_message(
            "Invalid tournament id (use the 8-character id from search).",
            ephemeral=True,
        )
        return

    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return

    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
        return

    if not member.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "Only members with **Manage Server** can set the followed tournament for everyone.",
            ephemeral=True,
        )
        return

    if bot.lichess is None:
        await interaction.response.send_message("Lichess client not ready.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    data_json = await bot.lichess.get_broadcast_tournament(tid)
    if not data_json:
        await interaction.followup.send("Could not load that tournament from Lichess.", ephemeral=True)
        return

    tour = data_json.get("tour") or {}
    tour_url = (tour.get("url") or "").strip() or f"{settings.LICHESS_SITE_BASE}/broadcast/-/-/{tid}"

    follow_storage.save_followed(tid, tour_url)
    if bot.monitor:
        bot.monitor.set_follow(tid, tour_url)

    name = tour.get("name") or tid
    await interaction.followup.send(
        f"**{interaction.guild.name}** is now following **{name}**.\n"
        f"Updates go to <#{settings.DISCORD_CHESS_CHANNEL_ID}>.",
        ephemeral=True,
    )
    logger.info("Guild %s followed broadcast %s", interaction.guild.id, tid)


class FollowTournamentButton(discord.ui.Button):
    def __init__(self, tournament_id: str, display_name: str, row: int) -> None:
        super().__init__(
            label=_button_label(display_name),
            style=discord.ButtonStyle.primary,
            custom_id=f"{FOLLOW_PREFIX}{tournament_id}",
            row=row,
        )
        self.tournament_id = tournament_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await _process_follow(interaction, self.tournament_id)


def _search_view(hits: list[dict]) -> discord.ui.View | None:
    view = discord.ui.View(timeout=3600)
    added = 0
    for i, hit in enumerate(hits[:5]):
        tour = hit.get("tour") or {}
        tid = tour.get("id")
        if not tid or not is_valid_broadcast_tournament_id(str(tid).strip()):
            continue
        tid = str(tid).strip()
        name = tour.get("name") or tid
        view.add_item(FollowTournamentButton(tid, name, row=added))
        added += 1
    if added == 0:
        return None
    return view


@bot.event
async def on_ready() -> None:
    logger.info("Online as %s", bot.user)
    if bot._setup_done:
        return
    bot._setup_done = True

    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s command(s)", len(synced))
    except Exception as e:
        logger.error("Sync failed: %s", e)

    if bot.lichess is None:
        bot.lichess = LichessClient(
            api_base=settings.LICHESS_API_BASE,
            cloud_eval_url=settings.LICHESS_CLOUD_EVAL_URL,
            site_base=settings.LICHESS_SITE_BASE,
            oauth_token=settings.LICHESS_API_TOKEN,
        )

    bid, url = follow_storage.load_followed()
    bot.monitor = TournamentMonitor(
        bot,
        settings.DISCORD_CHESS_CHANNEL_ID,
        settings.GROQ_API_KEY,
        lichess_client=bot.lichess,
        initial_broadcast_id=bid,
        initial_broadcast_url=url or "",
    )
    bot.monitor.start()
    logger.info("Monitor started (following: %s)", bid or "none")


@bot.tree.command(
    name="search",
    description="Search Lichess broadcasts (detailed); Follow sets the tournament for the whole server",
)
@app_commands.describe(query="Search text", page="Page 1–20")
async def cmd_search(interaction: discord.Interaction, query: str, page: int = 1) -> None:
    await interaction.response.defer()
    if bot.lichess is None:
        await interaction.followup.send("Lichess client not ready.", ephemeral=True)
        return

    api_page = await bot.lichess.search_broadcasts(query, page=page)
    if not api_page:
        await interaction.followup.send("Nothing came back from Lichess.")
        return

    results = api_page.get("currentPageResults") or []
    if not results:
        await interaction.followup.send("No results on that page.")
        return

    top = results[:5]

    async def _fetch_detail(hit: dict):
        tid = str((hit.get("tour") or {}).get("id") or "").strip()
        if not is_valid_broadcast_tournament_id(tid):
            return None
        return await bot.lichess.get_broadcast_tournament(tid)

    details = await asyncio.gather(*(_fetch_detail(h) for h in top))
    embeds: list[discord.Embed] = []
    for i, hit in enumerate(top):
        full = details[i] if i < len(details) else None
        if full and (full.get("tour") or {}).get("id"):
            embeds.append(embed_from_full_tournament(full, i + 1))
        else:
            embeds.append(embed_from_search_hit(hit, i + 1))
    view = _search_view(results)
    extra = (
        f"Page **{api_page.get('currentPage', page)}** — **{len(embeds)}** of **{len(results)}** on this page.\n"
        "**Follow** = entire server (requires **Manage Server**). Alerts post in the chess channel."
    )
    if api_page.get("nextPage"):
        extra += f"\nNext: `/search query:{query} page:{api_page['nextPage']}`"

    kwargs: dict = {"content": extra, "embeds": embeds}
    if view is not None:
        kwargs["view"] = view
    await interaction.followup.send(**kwargs)


@bot.tree.command(name="status", description="Bot and monitor status")
async def cmd_status(interaction: discord.Interaction) -> None:
    m = bot.monitor
    if m is None:
        await interaction.response.send_message("Monitor not ready yet.", ephemeral=True)
        return

    info = m.get_status()
    embed = discord.Embed(title="Maggie Man — status", color=0x5865F2)
    embed.add_field(name="Monitor", value="On" if info["running"] else "Off", inline=True)
    embed.add_field(name="Following", value="Yes" if info["following"] else "No", inline=True)
    embed.add_field(name="Broadcast ID", value=str(info["broadcast_id"]), inline=True)
    embed.add_field(name="Active games", value=str(info["active_games"]), inline=True)
    embed.add_field(name="Rounds tracked", value=str(info["rounds_tracked"]), inline=True)
    embed.add_field(name="Moves analysed", value=str(info["moves_analysed"]), inline=True)
    embed.add_field(name="Active round", value=str(info["active_round"] or "—"), inline=True)
    fb = info.get("followed_board")
    embed.add_field(
        name="Board follow",
        value=str(fb) if fb else "Off",
        inline=True,
    )
    url = info["broadcast_url"]
    if url and url != "—":
        embed.add_field(name="URL", value=url, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ask", description="Ask Maggie Man anything (short, plain-language reply)")
@app_commands.describe(question="Your question")
async def cmd_ask(interaction: discord.Interaction, question: str) -> None:
    q = question.strip()
    if len(q) < 2:
        await interaction.response.send_message("Ask something a bit longer.", ephemeral=True)
        return
    if len(q) > 1500:
        await interaction.response.send_message("That question is too long — shorten it?", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    reply = await generate_ask_reply(q, settings.GROQ_API_KEY, settings.GROQ_MODEL)
    if len(reply) > 2000:
        reply = reply[:1997] + "…"
    await interaction.followup.send(reply, ephemeral=True)


async def _process_game_follow(interaction: discord.Interaction, board: int) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
        return
    if not member.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "Only members with **Manage Server** can set board follow (same as tournament follow).",
            ephemeral=True,
        )
        return
    if bot.monitor is None:
        await interaction.response.send_message("Monitor not ready yet.", ephemeral=True)
        return

    if board <= 0:
        bot.monitor.set_followed_board(None)
        await interaction.response.send_message(
            "Board follow is **off**. No board will get every-move updates.",
            ephemeral=True,
        )
        return

    bot.monitor.set_followed_board(board)
    await interaction.response.send_message(
        f"Following **board {board}**: when a followed broadcast has a **live** round, each new move on that "
        f"board is posted to <#{settings.DISCORD_CHESS_CHANNEL_ID}> — Lichess cloud engine summary, "
        "Maggie's line, and the game PGN.\n"
        "(Set a tournament with **Follow** from `/search` if you have not already.)\n"
        "Use `/game board:0` to stop.",
        ephemeral=True,
    )
    logger.info("Guild %s set board follow to %s", interaction.guild.id, board)


@bot.tree.command(name="game", description="Follow one broadcast board: every move → engine + Maggie + PGN")
@app_commands.describe(
    board="Board number (1, 2, 3, …). Use 0 to turn off.",
)
async def cmd_game(interaction: discord.Interaction, board: int) -> None:
    await _process_game_follow(interaction, board)


@bot.tree.command(name="delete", description="Clear followed tournament, board follow, and saved settings")
async def cmd_delete(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
        return
    if not member.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "Only members with **Manage Server** can reset follow settings.",
            ephemeral=True,
        )
        return
    if bot.monitor is None:
        await interaction.response.send_message("Monitor not ready yet.", ephemeral=True)
        return

    bot.monitor.clear_all_follow_state()
    await interaction.response.send_message(
        "Removed the followed broadcast, board follow, and on-disk follow data. "
        "The bot is not tracking any tournament until you **Follow** again.",
        ephemeral=True,
    )
    logger.info("Guild %s cleared all follow state", interaction.guild.id)


@bot.tree.command(name="pair", description="List pairings for a broadcast round (from Lichess round PGN)")
@app_commands.describe(
    tournament_id="8-character tournament id from /search",
    round_number="Round number (1 = first scheduled round in the event)",
)
async def cmd_pair(interaction: discord.Interaction, tournament_id: str, round_number: int) -> None:
    await interaction.response.defer()
    if bot.lichess is None:
        await interaction.followup.send("Lichess client not ready.", ephemeral=True)
        return

    tid = tournament_id.strip()
    if not is_valid_broadcast_tournament_id(tid):
        await interaction.followup.send(
            "Invalid **tournament_id** — it must be the 8-character Lichess broadcast id (footer on /search)."
        )
        return

    data = await bot.lichess.get_broadcast_tournament(tid)
    if not data:
        await interaction.followup.send("Could not load that tournament from Lichess.")
        return

    rounds = sort_broadcast_rounds(data.get("rounds") or [])
    rnd = pick_round_by_index(rounds, round_number)
    if not rnd:
        await interaction.followup.send(
            f"There is no round **{round_number}**. This event lists **{len(rounds)}** round(s) (use 1–{len(rounds)})."
        )
        return

    rid = rnd.get("id")
    if not rid:
        await interaction.followup.send("That round has no id.")
        return

    pgn = await bot.lichess.get_round_pgn(str(rid))
    games, err = pairings_from_pgn(pgn)
    tour_name = (data.get("tour") or {}).get("name") or tid
    rname = rnd.get("name") or f"Round {round_number}"
    rurl = (rnd.get("url") or "").strip()

    header = (
        f"**{tour_name}** · **{rname}**\n{rurl}\n\n"
        if rurl
        else f"**{tour_name}** · **{rname}**\n\n"
    )

    if not games:
        await interaction.followup.send(header + (err or "No pairings found."))
        return

    body = format_pairings_text(games)
    if len(header) + len(body) <= 1900:
        await interaction.followup.send(header + body)
    else:
        await interaction.followup.send(
            header + f"_{len(games)} pairings — see file._",
            file=discord.File(io.BytesIO(body.encode("utf-8")), filename="pairings.txt"),
        )


def main() -> None:
    bot.run(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
