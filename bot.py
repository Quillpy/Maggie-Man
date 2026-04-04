from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands
from groq import Groq

import settings
from broadcast_ui import (
    embed_broadcast_round,
    embed_broadcast_tournament,
    embed_player_detail,
    embed_players_list,
    embed_from_search_hit,
    embed_team_standings,
)
from lichess_client import LichessClient
from monitor import TournamentMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("maggie-man")

intents = discord.Intents.default()
intents.message_content = True

MAGGIE_CHAT_SYSTEM = """
You're Maggie Man — sarcastic, casual, a bit smug (Magnus parody).
Answer in plain English, short. Dry jokes welcome. No lectures, no fake grandeur.
Chess talk only; don't be mean about real-world traits. If you don't know, say so.
"""


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
lichess_group = app_commands.Group(
    name="lichess",
    description="Lichess broadcast tools (see https://lichess.org/api#tag/broadcasts)",
)


@bot.event
async def on_ready() -> None:
    logger.info("Maggie Man online as %s", bot.user)
    if bot._setup_done:
        return
    bot._setup_done = True

    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s slash commands", len(synced))
    except Exception as e:
        logger.error("Command sync failed: %s", e)

    if bot.lichess is None:
        bot.lichess = LichessClient(
            api_base=settings.LICHESS_API_BASE,
            cloud_eval_url=settings.LICHESS_CLOUD_EVAL_URL,
            site_base=settings.LICHESS_SITE_BASE,
            oauth_token=settings.LICHESS_API_TOKEN,
        )

    channel = bot.get_channel(settings.DISCORD_CHESS_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="Maggie Man is here",
            description=(
                "I’ll spam the chess channel with **this** broadcast’s rounds, reminders, "
                "and the occasional roast when someone steps on a rake on the board.\n\n"
                "No `/follow` nonsense — it’s automatic.\n"
                "Use `/lichess search` to hunt other events, `/status` for my vitals, `/maggie` to annoy me."
            ),
            color=0xFFD700,
        )
        embed.add_field(
            name="Monitored broadcast",
            value=f"[Open on Lichess]({settings.MONITORED_BROADCAST_URL})\n`{settings.MONITORED_BROADCAST_ID}`",
            inline=False,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning("Could not send startup message: %s", e)

    bot.monitor = TournamentMonitor(
        bot,
        settings.DISCORD_CHESS_CHANNEL_ID,
        settings.GROQ_API_KEY,
        lichess_client=bot.lichess,
    )
    bot.monitor.start()
    logger.info("Tournament monitor started")


@bot.tree.command(name="status", description="Monitor status")
async def cmd_status(interaction: discord.Interaction) -> None:
    m = bot.monitor
    if m is None:
        await interaction.response.send_message("Monitor not up yet.", ephemeral=True)
        return
    info = m.get_status()
    embed = discord.Embed(title="Maggie Man status", color=0x5865F2)
    embed.add_field(
        name="Monitoring",
        value="On" if info["running"] else "Off",
        inline=True,
    )
    embed.add_field(name="Broadcast ID", value=str(info["broadcast_id"]), inline=True)
    embed.add_field(name="Active games", value=str(info["active_games"]), inline=True)
    embed.add_field(name="Rounds tracked", value=str(info["rounds_tracked"]), inline=True)
    embed.add_field(name="Moves analysed", value=str(info["moves_analysed"]), inline=True)
    embed.add_field(name="Active round", value=str(info["active_round"] or "—"), inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="maggie", description="Ask Maggie Man something (chess-ish)")
@app_commands.describe(question="What you want")
async def cmd_maggie(interaction: discord.Interaction, question: str) -> None:
    await interaction.response.defer()
    groq_client = Groq(api_key=settings.GROQ_API_KEY)
    try:
        completion = groq_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": MAGGIE_CHAT_SYSTEM},
                {"role": "user", "content": question},
            ],
            temperature=0.9,
            max_completion_tokens=400,
            top_p=1,
            stream=False,
        )
        answer = (completion.choices[0].message.content or "").strip() or "…"
        embed = discord.Embed(
            title="Maggie says",
            description=answer[:4096],
            color=0xFFD700,
        )
        embed.set_footer(text=f"Asked by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error("/maggie Groq error: %s", e)
        await interaction.followup.send(
            "Brain fog. Try again in a minute.",
            ephemeral=True,
        )


def _require_lichess(interaction: discord.Interaction) -> LichessClient | None:
    client = interaction.client
    if not isinstance(client, MaggieBot) or client.lichess is None:
        return None
    return client.lichess


@lichess_group.command(name="search", description="Search official broadcasts")
@app_commands.describe(query="Text to search", page="Page 1–20")
async def lichess_search(
    interaction: discord.Interaction,
    query: str,
    page: int = 1,
) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.search_broadcasts(query, page=page)
    if not data:
        await interaction.followup.send("Nothing came back. Try different words.")
        return
    results = data.get("currentPageResults") or []
    if not results:
        await interaction.followup.send("No hits on that page.")
        return
    embeds = [embed_from_search_hit(results[i], i + 1) for i in range(min(5, len(results)))]
    extra = f"Page **{data.get('currentPage', page)}** — showing **{len(embeds)}** of **{len(results)}** on this page."
    if data.get("nextPage"):
        extra += f" Next page: `/lichess search query:{query} page:{data['nextPage']}`"
    await interaction.followup.send(content=extra, embeds=embeds)


@lichess_group.command(
    name="tournament",
    description="Get a broadcast tournament by 8-character ID",
)
@app_commands.describe(tournament_id="8-char broadcast tournament ID")
async def lichess_tournament(
    interaction: discord.Interaction,
    tournament_id: str,
) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.get_broadcast_tournament(tournament_id.strip())
    if not data:
        await interaction.followup.send("Couldn’t load that tournament. Check the ID.")
        return
    await interaction.followup.send(embed=embed_broadcast_tournament(data))


@lichess_group.command(name="top", description="Paginated top broadcasts (lichess.org/broadcast)")
@app_commands.describe(page="Page 1–20 (page 1 = live/active list)")
async def lichess_top(interaction: discord.Interaction, page: int = 1) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.get_broadcast_top(page=page)
    if not data:
        await interaction.followup.send("Empty response from Lichess.")
        return
    if page <= 1:
        results = list(data.get("active") or [])[:15]
        header = "Live / active on Lichess right now"
    else:
        past = data.get("past")
        if isinstance(past, dict):
            results = list(past.get("currentPageResults") or [])[:15]
        else:
            results = list(past or [])[:15]
        header = f"Past broadcasts (API page **{page}**)"
    if not results:
        await interaction.followup.send("Nothing on that page.")
        return
    embeds = [embed_from_search_hit(hit, i + 1) for i, hit in enumerate(results[:5])]
    await interaction.followup.send(
        content=f"{header} — showing **{len(embeds)}** of **{len(results)}** pulled.",
        embeds=embeds,
    )


@lichess_group.command(
    name="official",
    description="First N lines from GET /api/broadcast (official feed, NDJSON)",
)
@app_commands.describe(nb="How many tournaments to fetch (1–100)")
async def lichess_official(interaction: discord.Interaction, nb: int = 10) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    rows = await lc.get_official_broadcasts(nb=max(1, min(100, nb)))
    if not rows:
        await interaction.followup.send("No data (or Lichess hiccuped).")
        return
    embeds = []
    for i, row in enumerate(rows[:5]):
        tour = row.get("tour") or {}
        rounds = row.get("rounds") or []
        rnd: dict = {}
        for r in rounds:
            if r.get("ongoing"):
                rnd = r
                break
        if not rnd and rounds:
            rnd = rounds[-1]
        embeds.append(embed_from_search_hit({"tour": tour, "round": rnd}, i + 1))
    await interaction.followup.send(
        content=f"Official feed — **{len(rows)}** tournament(s) fetched, showing **{len(embeds)}**.",
        embeds=embeds,
    )


@lichess_group.command(
    name="round",
    description="Round JSON (slugs can be “-”) — GET /api/broadcast/-/ -/{round_id}",
)
@app_commands.describe(round_id="8-char round ID")
async def lichess_round(interaction: discord.Interaction, round_id: str) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.get_broadcast_round(round_id.strip())
    if not data:
        await interaction.followup.send("Couldn’t load that round.")
        return
    await interaction.followup.send(embed=embed_broadcast_round(data))


@lichess_group.command(name="players", description="Players in a broadcast tournament")
@app_commands.describe(tournament_id="8-char tournament ID")
async def lichess_players(interaction: discord.Interaction, tournament_id: str) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    players = await lc.get_broadcast_players(tournament_id.strip())
    if players is None:
        await interaction.followup.send("No player list (or not found).")
        return
    await interaction.followup.send(embed=embed_players_list(players))


@lichess_group.command(name="player", description="One player from a broadcast")
@app_commands.describe(tournament_id="8-char tournament ID", player_id="Player id from /lichess players")
async def lichess_player(
    interaction: discord.Interaction,
    tournament_id: str,
    player_id: str,
) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.get_broadcast_player(tournament_id.strip(), player_id.strip())
    if not data:
        await interaction.followup.send("Player not found.")
        return
    await interaction.followup.send(embed=embed_player_detail(data))


@lichess_group.command(name="standings", description="Team leaderboard for a broadcast")
@app_commands.describe(tournament_id="8-char tournament ID")
async def lichess_standings(interaction: discord.Interaction, tournament_id: str) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    rows = await lc.get_broadcast_team_standings(tournament_id.strip())
    if rows is None:
        await interaction.followup.send("No standings (or not found).")
        return
    await interaction.followup.send(embed=embed_team_standings(rows))


@lichess_group.command(
    name="by_user",
    description="Broadcasts created by a Lichess user (OAuth improves visibility)",
)
@app_commands.describe(username="Lichess username", page="Page number")
async def lichess_by_user(
    interaction: discord.Interaction,
    username: str,
    page: int = 1,
) -> None:
    await interaction.response.defer()
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    data = await lc.get_broadcasts_by_user(username.strip(), page=page)
    if not data:
        await interaction.followup.send("Nothing returned.")
        return
    results = data.get("currentPageResults") or []
    if not results:
        await interaction.followup.send("No broadcasts for that user on this page.")
        return
    embeds = []
    for i, item in enumerate(results[:5]):
        tour = item if item.get("name") else item.get("tour") or item
        url = tour.get("url", "")
        name = tour.get("name", "Broadcast")
        embeds.append(
            discord.Embed(title=f"{i + 1}. {name}", url=url or None, color=0x5865F2)
        )
    await interaction.followup.send(
        content=f"`{username}` — page **{data.get('currentPage', page)}**.",
        embeds=embeds,
    )


@lichess_group.command(
    name="pgn",
    description="Links to export PGN (full tournament or one round)",
)
@app_commands.describe(
    tournament_id="8-char tournament ID (optional)",
    round_id="8-char round ID (optional)",
)
async def lichess_pgn(
    interaction: discord.Interaction,
    tournament_id: str | None = None,
    round_id: str | None = None,
) -> None:
    base = settings.LICHESS_API_BASE
    lines = []
    if round_id and round_id.strip():
        rid = round_id.strip()
        lines.append(
            f"**Round PGN:** {base}/broadcast/round/{rid}.pgn\n"
            f"**Stream (live):** {base}/stream/broadcast/round/{rid}.pgn"
        )
    if tournament_id and tournament_id.strip():
        tid = tournament_id.strip()
        lines.append(f"**All rounds PGN:** {base}/broadcast/{tid}.pgn")
    if not lines:
        await interaction.response.send_message(
            "Give at least one of `tournament_id` or `round_id`.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        "\n\n".join(lines) + "\n\n*(Open in browser or curl — files can be huge.)*"
    )


@lichess_group.command(
    name="my_rounds",
    description="Your broadcast rounds (needs LICHESS_API_TOKEN with study:read)",
)
@app_commands.describe(nb="How many rows to pull")
async def lichess_my_rounds(interaction: discord.Interaction, nb: int = 15) -> None:
    await interaction.response.defer(ephemeral=True)
    if not settings.LICHESS_API_TOKEN:
        await interaction.followup.send(
            "Set `LICHESS_API_TOKEN` on the server (OAuth, scope `study:read`).",
            ephemeral=True,
        )
        return
    lc = _require_lichess(interaction)
    if not lc:
        await interaction.followup.send("API client not ready.", ephemeral=True)
        return
    rows = await lc.get_my_broadcast_rounds(nb=max(1, min(50, nb)))
    if not rows:
        await interaction.followup.send(
            "No rows. Token wrong/expired, or you’re not in any rounds.",
            ephemeral=True,
        )
        return
    text_lines = []
    for r in rows[:20]:
        tour = r.get("tournament") or r.get("tour") or {}
        rnd = r.get("round") or r
        name = tour.get("name", "?")
        rn = rnd.get("name", "?")
        url = rnd.get("url") or tour.get("url") or ""
        text_lines.append(f"• **{name}** — {rn}\n  {url}")
    await interaction.followup.send(
        "\n".join(text_lines)[:1900] or "…",
        ephemeral=True,
    )


bot.tree.add_command(lichess_group)


def main() -> None:
    bot.run(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
