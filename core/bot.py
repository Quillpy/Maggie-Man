from __future__ import annotations

import asyncio
import io
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import settings
from api.lichess import LichessClient
from core.monitor import TournamentMonitor
from storage.follow import load_followed, save_followed
from utils.engine import is_valid_broadcast_tournament_id
from utils.ui import embed_from_full_tournament, embed_from_search_hit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

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

    save_followed(tid, tour_url)
    if bot.monitor:
        bot.monitor.set_follow(tid, tour_url)

    name = tour.get("name") or tid
    await interaction.followup.send(
        f"**{interaction.guild.name}** is now following **{name}**.\n"
        f"Updates go to <#{settings.DISCORD_CHESS_CHANNEL_ID}>.",
        ephemeral=True,
    )
    logger.info("Followed broadcast %s", tid)


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
    except Exception:
        pass

    if bot.lichess is None:
        bot.lichess = LichessClient(
            api_base=settings.LICHESS_API_BASE,
            cloud_eval_url=settings.LICHESS_CLOUD_EVAL_URL,
            site_base=settings.LICHESS_SITE_BASE,
            oauth_token=settings.LICHESS_API_TOKEN,
        )

    bid, url = load_followed()
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
    description="Search Lichess tournaments. Follow sets for the whole server (Manage Server).",
)
@app_commands.describe(query="Search query", page="Page 1–20")
async def cmd_search(interaction: discord.Interaction, query: str, page: int = 1) -> None:
    await interaction.response.defer()
    if bot.lichess is None:
        await interaction.followup.send("Lichess client not ready.", ephemeral=True)
        return

    api_page = await bot.lichess.search_broadcasts(query, page=page)
    if not api_page:
        await interaction.followup.send("Nothing from Lichess.")
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
        f"Page **{api_page.get('currentPage', page)}** — **{len(embeds)}** results.\n"
        "**Follow** = entire server (Manage Server). Alerts in chess channel."
    )
    if api_page.get("nextPage"):
        extra += f"\nNext: `/search query:{query} page:{api_page['nextPage']}`"

    kwargs = {"content": extra, "embeds": embeds}
    if view is not None:
        kwargs["view"] = view
    await interaction.followup.send(**kwargs)


@bot.tree.command(name="status", description="Bot status (ephemeral)")
async def cmd_status(interaction: discord.Interaction) -> None:
    m = bot.monitor
    if m is None:
        await interaction.response.send_message("Monitor not ready.", ephemeral=True)
        return

    info = m.get_status()
    embed = discord.Embed(title="Maggie Man status", color=0x5865F2)
    embed.add_field(name="Monitor", value="On" if info["running"] else "Off", inline=True)
    embed.add_field(name="Following", value="Yes" if info["following"] else "No", inline=True)
    embed.add_field(name="Broadcast ID", value=str(info["broadcast_id"]), inline=True)
    embed.add_field(name="Active games", value=str(info["active_games"]), inline=True)
    embed.add_field(name="Rounds tracked", value=str(info["rounds_tracked"]), inline=True)
    embed.add_field(name="Moves analysed", value=str(info["moves_analysed"]), inline=True)
    embed.add_field(name="Active round", value=str(info["active_round"] or "—"), inline=True)
    url = info["broadcast_url"]
    if url and url != "—":
        embed.add_field(name="URL", value=url, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


def main() -> None:
    bot.run(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()

