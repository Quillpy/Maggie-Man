"""Format Lichess broadcast API data for Discord embeds."""

from __future__ import annotations

from datetime import datetime, timezone

import discord


def _ms_to_dt(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def format_lichess_time(ms: int | float | None) -> str:
    dt = _ms_to_dt(ms)
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _truncate(s: str, max_len: int = 1020) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def tour_info_lines(tour: dict) -> str:
    info = tour.get("info") or {}
    lines: list[str] = []
    if tour.get("name"):
        lines.append(f"**{tour['name']}**")
    if info.get("format"):
        lines.append(f"Format: {info['format']}")
    if info.get("tc"):
        lines.append(f"Time control: {info['tc']}")
    if info.get("fideTC"):
        lines.append(f"FIDE TC: {info['fideTC']}")
    if info.get("location"):
        lines.append(f"Location: {info['location']}")
    if info.get("timeZone"):
        lines.append(f"Time zone: {info['timeZone']}")
    dates = tour.get("dates") or []
    if len(dates) >= 1:
        lines.append(f"Starts: {format_lichess_time(dates[0])}")
    if len(dates) >= 2:
        lines.append(f"Ends: {format_lichess_time(dates[1])}")
    if tour.get("url"):
        lines.append(f"[Broadcast]({tour['url']})")
    return _truncate("\n".join(lines))


def embed_from_search_hit(hit: dict, index: int) -> discord.Embed:
    """One search / top result: { tour, round } shape."""
    tour = hit.get("tour") or {}
    rnd = hit.get("round") or {}
    title = tour.get("name") or "Broadcast"
    emb = discord.Embed(
        title=f"{index}. {title}",
        description=tour_info_lines(tour),
        color=0x5865F2,
        url=tour.get("url"),
    )
    if rnd.get("name"):
        emb.add_field(
            name="Latest / listed round",
            value=_truncate(
                f"{rnd.get('name', '')}\n"
                f"Starts: {format_lichess_time(rnd.get('startsAt'))}\n"
                f"{rnd.get('url', '')}"
            ),
            inline=False,
        )
    if tour.get("id"):
        emb.set_footer(text=f"Tournament ID: {tour['id']}")
    return emb


def embed_broadcast_tournament(data: dict) -> discord.Embed:
    """Full GET /api/broadcast/{{id}} response."""
    tour = data.get("tour") or {}
    title = tour.get("name") or "Broadcast tournament"
    emb = discord.Embed(
        title=title,
        description=tour_info_lines(tour),
        color=0xFFD700,
        url=tour.get("url"),
    )
    rounds = data.get("rounds") or []
    lines: list[str] = []
    for r in rounds[:20]:
        st = "🔴 live" if r.get("ongoing") else ("✓ done" if r.get("finished") else "⏳")
        lines.append(
            f"{st} **{r.get('name', '?')}** — {format_lichess_time(r.get('startsAt'))} "
            f"`{r.get('id', '')}`"
        )
    if len(rounds) > 20:
        lines.append(f"… and {len(rounds) - 20} more rounds")
    emb.add_field(
        name=f"Rounds ({len(rounds)})",
        value=_truncate("\n".join(lines) if lines else "No rounds listed."),
        inline=False,
    )
    if tour.get("id"):
        emb.set_footer(text=f"Tournament ID: {tour['id']}")
    return emb


def embed_broadcast_round(data: dict) -> discord.Embed:
    rnd = data.get("round") or data
    name = rnd.get("name") or data.get("name") or "Round"
    url = rnd.get("url") or data.get("url")
    emb = discord.Embed(title=name, color=0x5865F2, url=url)
    emb.add_field(
        name="Starts",
        value=format_lichess_time(rnd.get("startsAt")),
        inline=True,
    )
    emb.add_field(
        name="Ongoing",
        value=str(rnd.get("ongoing", False)),
        inline=True,
    )
    emb.add_field(
        name="Finished",
        value=str(rnd.get("finished", False)),
        inline=True,
    )
    games = data.get("games") or []
    if games:
        glines = []
        for g in games[:12]:
            pl = g.get("players") or []
            if len(pl) >= 2:
                w = pl[0].get("name", "?")
                b = pl[1].get("name", "?")
                glines.append(f"{w} vs {b}")
            elif g.get("name"):
                glines.append(g["name"])
            else:
                glines.append(str(g.get("id", "?")))
        if len(games) > 12:
            glines.append(f"… +{len(games) - 12} games")
        emb.add_field(name="Games", value=_truncate("\n".join(glines)), inline=False)
    rid = rnd.get("id") or data.get("id")
    if rid:
        emb.set_footer(text=f"Round ID: {rid}")
    return emb


def embed_players_list(players: list) -> discord.Embed:
    emb = discord.Embed(title="Broadcast players", color=0x5865F2)
    lines = []
    for p in players[:25]:
        if isinstance(p, dict):
            name = p.get("name") or p.get("id") or str(p)
            lines.append(name)
        else:
            lines.append(str(p))
    if len(players) > 25:
        lines.append(f"… +{len(players) - 25} more")
    emb.description = _truncate("\n".join(lines) if lines else "No players.")
    emb.set_footer(text=f"{len(players)} players")
    return emb


def embed_player_detail(data: dict) -> discord.Embed:
    name = data.get("name") or data.get("id") or "Player"
    emb = discord.Embed(title=name, color=0x5865F2)
    for key in ("fideId", "fed", "rating", "title"):
        if data.get(key) is not None:
            emb.add_field(name=key, value=str(data[key]), inline=True)
    games = data.get("games") or []
    if games:
        emb.add_field(name="Games", value=str(len(games)), inline=True)
    emb.description = _truncate(str(data.get("bio") or data.get("description") or ""))
    return emb


def embed_team_standings(rows: list) -> discord.Embed:
    emb = discord.Embed(title="Team standings", color=0x5865F2)
    lines = []
    for i, row in enumerate(rows[:20], 1):
        if isinstance(row, dict):
            team = row.get("team") or row.get("name") or str(row)
            score = row.get("score", row.get("points", ""))
            lines.append(f"{i}. {team} — {score}")
        else:
            lines.append(str(row))
    emb.description = _truncate("\n".join(lines) if lines else "No standings.")
    return emb
