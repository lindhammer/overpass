"""HTML briefing renderer – renders Jinja2 template and saves to disk."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from overpass.editorial.digest import DigestOutput
from overpass.collectors.base import CollectorItem

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "briefings"

# Map collector source ids to the human-readable labels shown in the colophon.
_SOURCE_LABELS: dict[str, str] = {
    "hltv": "HLTV",
    "reddit": "r/GlobalOffensive",
    "youtube": "YouTube",
    "steam": "Steam News",
    "podcast": "Podcasts",
}

# Matches BBCode tags like [b], [/b], [h1], [list], [*], [url=...], etc.
_BBCODE_RE = re.compile(r"\[/?[a-zA-Z0-9]+(?:=[^\]]+)?\]")

# Common multi-word team-name aliases that map to the established short codes
# used by the template's per-team crest tints.
_TEAM_CODE_OVERRIDES: dict[str, str] = {
    "vitality": "VIT",
    "team vitality": "VIT",
    "mongolz": "MZ",
    "the mongolz": "MZ",
    "parivision": "PV",
    "spirit": "SP",
    "team spirit": "SP",
    "natus vincere": "NAVI",
    "navi": "NAVI",
    "faze": "FAZE",
    "faze clan": "FAZE",
    "g2": "G2",
    "g2 esports": "G2",
    "furia": "FUR",
    "furia esports": "FUR",
    "astralis": "AST",
    "team liquid": "LIQ",
    "liquid": "LIQ",
    "heroic": "HER",
    "pain": "PAI",
    "pain gaming": "PAI",
    "ence": "ENC",
    "nip": "NIP",
    "ninjas in pyjamas": "NIP",
}


def _first_paragraph(text: str, max_chars: int = 300) -> str:
    """Strip BBCode markup and return the first non-empty paragraph."""
    clean = _BBCODE_RE.sub("", text).strip()
    for sep in ("\n\n", "\n"):
        parts = [p.strip() for p in clean.split(sep) if p.strip()]
        if parts:
            first = parts[0]
            return first if len(first) <= max_chars else first[:max_chars].rstrip() + "…"
    return clean[:max_chars].rstrip() + ("…" if len(clean) > max_chars else "")


def _team_code(name: str | None) -> str:
    """Return a short crest label for a team name (2-4 uppercase letters)."""
    if not name:
        return "??"
    key = name.strip().lower()
    if key in _TEAM_CODE_OVERRIDES:
        return _TEAM_CODE_OVERRIDES[key]
    letters = "".join(ch for ch in name if ch.isalpha())
    if not letters:
        return "??"
    return letters[:3].upper()


def _fmt_date(value: date | datetime, fmt: str) -> str:
    """Cross-platform strftime that translates `%-d` / `%-H` etc. on Windows."""
    if os.name == "nt":
        fmt = (
            fmt.replace("%-d", "%#d")
            .replace("%-H", "%#H")
            .replace("%-I", "%#I")
            .replace("%-m", "%#m")
            .replace("%-M", "%#M")
            .replace("%-S", "%#S")
            .replace("%-j", "%#j")
        )
    return value.strftime(fmt)


def _compute_issue_number(briefing_date: date) -> int:
    """Return the 1-indexed issue number based on briefings already on disk.

    Counts every distinct YYYY-MM-DD HTML file currently in the output folder
    plus the briefing being rendered (if it doesn't exist yet). This stays
    stable as long as old briefings are kept, and never invents issues for
    days the project wasn't actually run.
    """
    target_name = f"{briefing_date.isoformat()}.html"
    if not _OUTPUT_DIR.exists():
        return 1

    existing_dates: set[str] = set()
    for path in _OUTPUT_DIR.glob("*.html"):
        stem = path.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            existing_dates.add(stem)
    existing_dates.add(briefing_date.isoformat())
    return len(existing_dates)


def _collect_sources(digest: DigestOutput) -> list[str]:
    """Return colophon-ready list of source labels actually represented in the digest."""
    seen: list[str] = []
    for section in digest.sections.values():
        for item in section.items:
            label = _SOURCE_LABELS.get(item.source, item.source.title())
            if label not in seen:
                seen.append(label)
    return seen


def _build_ticker_chips(digest: DigestOutput) -> list[dict[str, str]]:
    """Build the masthead ticker chips from the digest's match section."""
    chips: list[dict[str, str]] = []
    matches_section = digest.sections.get("Matches")
    if not matches_section or not matches_section.items:
        return chips

    items = matches_section.items
    live_count = sum(1 for it in items if "live" in (it.metadata.get("flags") or []))
    upset_count = sum(1 for it in items if "upset" in (it.metadata.get("flags") or []))
    watch_wins = [it for it in items if "watch" in (it.metadata.get("flags") or [])]

    if live_count:
        chips.append({"kind": "live", "text": f"{live_count} live match{'es' if live_count != 1 else ''}"})

    for it in watch_wins[:1]:
        winner = it.metadata.get("winner_name") or it.metadata.get("team1_name") or "Watchlist team"
        chips.append({"kind": "up", "text": f"{winner} advanced"})

    if upset_count:
        chips.append({
            "kind": "amber",
            "text": f"{upset_count} upset{'s' if upset_count != 1 else ''}",
        })

    return chips


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["first_paragraph"] = _first_paragraph
    env.filters["team_code"] = _team_code
    env.filters["fmt_date"] = _fmt_date
    return env


def _social_post_to_dict(item: CollectorItem) -> dict[str, Any]:
    """Flatten a social CollectorItem into the dict shape the template expects."""
    md = item.metadata or {}
    return {
        "url": item.url,
        "handle": md.get("handle") or "",
        "display_name": md.get("display_name") or md.get("handle") or "",
        "verified": bool(md.get("verified", False)),
        "posted_at": item.timestamp,
        "body": md.get("body") or item.title,
        "context": md.get("context"),
        "avatar_seed": md.get("avatar_seed") or md.get("handle"),
        "team_color": md.get("team_color"),
    }


def render_briefing(
    digest: DigestOutput,
    briefing_date: date,
    *,
    social_items: list[CollectorItem] | None = None,
) -> str:
    """Render the briefing template and return the HTML string."""
    env = _make_env()
    template = env.get_template("briefing.html")
    social_posts = [_social_post_to_dict(it) for it in (social_items or [])]
    context: dict[str, Any] = {
        "digest": digest,
        "date": briefing_date,
        "generated_at": datetime.now(),
        "issue_no": _compute_issue_number(briefing_date),
        "ticker_chips": _build_ticker_chips(digest),
        "sources": _collect_sources(digest),
        "social_posts": social_posts,
        "per_match_blurbs": {
            url: blurb.model_dump() for url, blurb in digest.per_match_blurbs.items()
        },
    }
    return template.render(**context)


def save_briefing(html: str, briefing_date: date) -> Path:
    """Write the rendered HTML to output/briefings/{date}.html and return its path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"{briefing_date.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return path
