from __future__ import annotations

from datetime import datetime, timezone

import discord

from pairings import sort_broadcast_rounds


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


def tour_info_lines(tour: dict, *, include_name: bool = True) -> str:
    info = tour.get("info") or {}
    lines: list[str] = []
    if include_name and tour.get("name"):
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
    if info.get("players"):
        lines.append(f"Players: {_truncate(info['players'], 400)}")
    if info.get("website"):
        lines.append(f"Website: {info['website']}")
    if info.get("standings"):
        lines.append(f"Standings: {info['standings']}")
    dates = tour.get("dates") or []
    if len(dates) >= 1:
        lines.append(f"Starts: {format_lichess_time(dates[0])}")
    if len(dates) >= 2:
        lines.append(f"Ends: {format_lichess_time(dates[1])}")
    if tour.get("tier") is not None:
        lines.append(f"Tier: {tour['tier']}")
    if tour.get("url"):
        lines.append(f"[Broadcast]({tour['url']})")
    return _truncate("\n".join(lines))


def _round_line(r: dict, idx: int) -> str:
    name = r.get("name") or f"Round {idx}"
    start = format_lichess_time(r.get("startsAt"))
    bits = [f"**{idx}.** {name}", f"starts {start}"]
    if r.get("finished"):
        bits.append("(finished)")
    elif r.get("ongoing") or r.get("started"):
        bits.append("(live)")
    url = r.get("url")
    if url:
        bits.append(f"[link]({url})")
    return " · ".join(bits)


def embed_from_full_tournament(api: dict, index: int) -> discord.Embed:
    """Rich embed from GET /api/broadcast/{{id}} JSON."""
    tour = api.get("tour") or {}
    title = tour.get("name") or "Broadcast"
    desc_parts: list[str] = []

    if tour.get("description"):
        desc_parts.append(_truncate(tour["description"], 1800))

    desc_parts.append(tour_info_lines(tour, include_name=False))
    description = _truncate("\n\n".join(p for p in desc_parts if p), 4000)

    emb = discord.Embed(
        title=f"{index}. {title}",
        description=description,
        color=0x5865F2,
        url=tour.get("url"),
    )

    rounds = sort_broadcast_rounds(api.get("rounds") or [])
    if rounds:
        chunks: list[str] = []
        current = ""
        for i, r in enumerate(rounds, start=1):
            line = _round_line(r, i)
            if len(current) + len(line) + 1 > 950:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)
        for ci, chunk in enumerate(chunks[:4]):
            emb.add_field(
                name="Rounds" if ci == 0 else f"Rounds (cont. {ci + 1})",
                value=_truncate(chunk, 1020),
                inline=False,
            )
        if len(chunks) > 4:
            emb.add_field(
                name="Note",
                value=f"+ {len(chunks) - 4} more round block(s) — open the broadcast on Lichess.",
                inline=False,
            )

    dr = api.get("defaultRoundId")
    if dr:
        emb.add_field(name="Default round id", value=f"`{dr}`", inline=True)

    grp = api.get("group")
    if isinstance(grp, dict) and grp.get("name"):
        emb.add_field(name="Group", value=_truncate(str(grp.get("name")), 200), inline=True)

    tid = tour.get("id")
    if tid:
        emb.set_footer(text=f"Tournament id: {tid} — use with /pair")

    if tour.get("image"):
        emb.set_thumbnail(url=tour["image"])

    return emb


def embed_from_search_hit(hit: dict, index: int) -> discord.Embed:
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
            name="Round (search snapshot)",
            value=_truncate(
                f"{rnd.get('name', '')}\n"
                f"Starts: {format_lichess_time(rnd.get('startsAt'))}\n"
                f"{rnd.get('url', '')}"
            ),
            inline=False,
        )
    tid = tour.get("id")
    if tid:
        emb.set_footer(text=f"Tournament id: {tid}")
    return emb
