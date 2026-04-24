"""Render the Jinja2 briefing template to a static HTML briefing file."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from overpass.editorial.digest import DigestOutput
from overpass.collectors.base import CollectorItem
from overpass.history.models import HistoryEntry

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "briefings"

# Centralised strftime format strings used by the template. These are passed
# through the template context so format choices live in one place.
_DATE_FMT_HEADER = "%a %-d %b %Y"     # masthead + <title>: "WED 24 APR 2026"
_DATE_FMT_FOOTER = "%a %-d %b %Y · %H:%M"  # colophon line
_DATE_FMT_TIME = "%H:%M"               # "Filed HH:MM" line

# Map collector source ids to the human-readable labels shown in the colophon.
_SOURCE_LABELS: dict[str, str] = {
    "hltv": "HLTV",
    "reddit": "r/GlobalOffensive",
    "youtube": "YouTube",
    "steam": "Steam News",
    "podcast": "Podcasts",
}

# Ordered catalogue of briefing sections. Order here defines the on-page order,
# the jumpbar order, and the route-stops order. ``always_on`` sections always
# render (showing an empty-state tile when no items are available); other
# sections collapse silently when their data isn't present.
_SECTION_BLOCKS: list[dict[str, Any]] = [
    {"key": "Matches", "title": "Match Results", "kind": "matches",
     "blurb": "Last 24h. Taglines and key-player highlights.",
     "always_on": True, "source": "section"},
    {"key": "Clips", "title": "Top Clips", "kind": "clips",
     "blurb": "Reddit moments worth opening before the algorithm buries them.",
     "always_on": False, "source": "section"},
    {"key": "Social", "title": "Social", "kind": "social",
     "blurb": "Notable pro posts from the last 24 hours.",
     "always_on": False, "source": "social_posts"},
    {"key": "News", "title": "Roster Moves & News", "kind": "news",
     "blurb": "Team changes, management hints, announcement smoke.",
     "always_on": True, "source": "section"},
    {"key": "Upcoming", "title": "Upcoming", "kind": "upcoming",
     "blurb": "Scheduled fixtures. Click through to HLTV for streams and stats.",
     "always_on": True, "source": "upcoming_matches"},
    # Drops / Videos / Podcasts are resolved at build time: if both Videos and
    # Podcasts have items, we emit a single merged "Drops" block; otherwise we
    # emit whichever is present (or neither).
    {"key": "Drops", "title": "Content Drops", "kind": "drops",
     "blurb": "Long-form videos and podcasts from the last cycle.",
     "always_on": False, "source": "drops"},
    {"key": "Patches", "title": "Patch Notes", "kind": "patches",
     "blurb": "Latest game updates and balance changes.",
     "always_on": False, "source": "section"},
    {"key": "History", "title": "This Day in CS", "kind": "history",
     "blurb": "A moment from this date in Counter-Strike history.",
     "always_on": False, "source": "this_day"},
]

# Per-section show-more thresholds. Blocks not listed here render every item
# inline (no <details> wrapper).
_SECTION_LIMITS: dict[str, int] = {
    "matches": 6,
    "clips": 5,
    "news": 8,
    "drops": 6,
    "videos": 4,
    "podcasts": 4,
}

# Matches BBCode tags like [b], [/b], [h1], [list], [*], [url=...], etc.
_BBCODE_RE = re.compile(r"\[/?[a-zA-Z0-9]+(?:=[^\]]+)?\]")

# Patterns used by _clean_drop to strip noise from YouTube / podcast blurbs.
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HASHTAG_RUN_RE = re.compile(r"(?:#\w+\s*){2,}")
_LONE_HASHTAG_RE = re.compile(r"#\w+")
_BOILERPLATE_RE = re.compile(
    r"\b(?:please\s+)?(?:subscribe|like\s+and\s+subscribe|hit\s+that\s+(?:like|bell)|"
    r"smash(?:\s+the)?\s+like|follow\s+us|follow\s+me|check\s+out\s+our|"
    r"join\s+our\s+discord|use\s+code\s+\w+|sponsored\s+by\b[^.]*)\.?",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
# Real YouTube IDs are exactly 11 chars from [A-Za-z0-9_-].
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})(?:[^A-Za-z0-9_-]|$)")

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


def _section_count(
    block: dict[str, Any],
    digest: DigestOutput,
    social_posts: list[Any],
    upcoming_matches: list[Any],
    this_day: HistoryEntry | None,
) -> int:
    """Return the item count a block will render for its current data."""
    src = block["source"]
    if src == "section":
        section = digest.sections.get(block["key"])
        return len(section.items) if section else 0
    if src == "social_posts":
        return len(social_posts)
    if src == "upcoming_matches":
        return len(upcoming_matches)
    if src == "this_day":
        return 1 if this_day is not None else 0
    if src == "drops":
        videos = digest.sections.get("Videos")
        pods = digest.sections.get("Podcasts")
        return (len(videos.items) if videos else 0) + (len(pods.items) if pods else 0)
    return 0


def _build_blocks(
    digest: DigestOutput,
    social_posts: list[Any],
    upcoming_matches: list[Any],
    this_day: HistoryEntry | None,
) -> list[dict[str, Any]]:
    """Resolve _SECTION_BLOCKS against the current briefing's data.

    Drops/Videos/Podcasts are special-cased: when both Videos and Podcasts have
    items the merged "Drops" block is emitted; otherwise the present sub-section
    (if any) takes its place. Always-on blocks are kept regardless of count.
    """
    has_videos = bool(digest.sections.get("Videos") and digest.sections["Videos"].items)
    has_pods = bool(digest.sections.get("Podcasts") and digest.sections["Podcasts"].items)

    out: list[dict[str, Any]] = []
    for block in _SECTION_BLOCKS:
        if block["kind"] == "drops":
            resolved: dict[str, Any] | None = None
            if has_videos and has_pods:
                resolved = {**block}
            elif has_videos:
                resolved = {
                    "key": "Videos", "title": "Videos", "kind": "videos",
                    "blurb": "Long-form videos worth your watch-later list.",
                    "always_on": False, "source": "section",
                }
            elif has_pods:
                resolved = {
                    "key": "Podcasts", "title": "Podcasts", "kind": "podcasts",
                    "blurb": "Episodes dropped in the last cycle.",
                    "always_on": False, "source": "section",
                }
            if resolved is not None:
                resolved["count"] = _section_count(
                    resolved, digest, social_posts, upcoming_matches, this_day,
                )
                out.append(resolved)
            continue

        count = _section_count(block, digest, social_posts, upcoming_matches, this_day)
        if count > 0 or block.get("always_on"):
            out.append({**block, "count": count})
    return out


def _build_route_stops(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Auto-derive masthead route stops from the resolved block list.

    Each stop's body uses the section's editorial blurb when present, prefixed
    with the item count (e.g. "6 \u00b7 Last 24h. Taglines and key-player highlights.").
    Falls back to a plain count line when no blurb is configured.
    """
    stops: list[dict[str, str]] = []
    for block in blocks[:4]:
        count = block.get("count", 0)
        blurb = (block.get("blurb") or "").strip()
        if blurb:
            body = f"{count} \u00b7 {blurb}" if count else blurb
        else:
            label = "item" if count == 1 else "items"
            body = f"{count} {label} queued." if count else "Briefing stop."
        stops.append({"title": block["title"], "body": body})
    return stops


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["first_paragraph"] = _first_paragraph
    env.filters["team_code"] = _team_code
    env.filters["fmt_date"] = _fmt_date
    env.filters["news_category"] = _classify_news
    env.filters["news_category_label"] = _news_category_label
    env.filters["pluralize"] = _pluralize
    env.filters["clean_drop"] = _clean_drop
    env.filters["youtube_thumb"] = _youtube_thumb
    return env


# Heuristic news classification.
# - "alert" (red): integrity / bans / cheating / suspensions / leaks
# - "trade" (yellow): roster moves, signings, departures, free agency
# - "default" (amber): everything else
_NEWS_ALERT_PATTERNS = re.compile(
    r"\b(esic|ban|bans|banned|cheat|cheating|cheater|suspend|suspended|"
    r"suspension|integrity|match[- ]fix|matchfixing|leak|leaked|doxx|"
    r"vac|valve ban|investigation)\b",
    re.IGNORECASE,
)
_NEWS_TRADE_PATTERNS = re.compile(
    r"\b(sign|signs|signed|signing|join|joins|joined|part ways|parts ways|"
    r"depart|departs|departure|leave|leaves|left|free agency|free agent|"
    r"benched?|bench|stand[- ]in|stands? in|stand-in|loan|loaned|trial|"
    r"transfer|transfers|trade|trades|coach|coaches|return|returns|"
    r"reveal|unveil|announce roster|new roster|rebuild|disband|disbands)\b",
    re.IGNORECASE,
)


def _classify_news(item: CollectorItem | dict[str, Any] | None) -> str:
    """Return 'alert' | 'trade' | 'default' for a news item.

    Honours an explicit ``metadata.category`` if present; otherwise classifies
    heuristically from the headline.
    """
    if item is None:
        return "default"
    if isinstance(item, dict):
        md = item.get("metadata") or {}
        title = item.get("title") or ""
    else:
        md = item.metadata or {}
        title = item.title or ""
    category = (md.get("category") or "").strip().lower()
    if category in ("alert", "trade", "default"):
        return category
    if _NEWS_ALERT_PATTERNS.search(title):
        return "alert"
    if _NEWS_TRADE_PATTERNS.search(title):
        return "trade"
    return "default"


def _news_category_label(item: CollectorItem | dict[str, Any] | None) -> str:
    """Return a short uppercase ribbon label for a news item."""
    if item is None:
        return "News"
    if isinstance(item, dict):
        md = item.get("metadata") or {}
    else:
        md = item.metadata or {}
    explicit = (md.get("category_label") or "").strip()
    if explicit:
        return explicit
    return {
        "alert": "Alert",
        "trade": "Roster",
        "default": "News",
    }[_classify_news(item)]


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Return ``singular`` if count == 1, else ``plural`` (or singular + 's')."""
    if count == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


def _clean_drop(text: str | None, max_chars: int = 180) -> str:
    """Sanitise a YouTube/podcast description for compact card display.

    Removes URLs, emails, runs of hashtags, common subscribe/follow boilerplate,
    collapses whitespace, then truncates to ``max_chars`` on a word boundary
    with an ellipsis when needed.
    """
    if not text:
        return ""
    s = _URL_RE.sub("", text)
    s = _EMAIL_RE.sub("", s)
    s = _BOILERPLATE_RE.sub("", s)
    s = _HASHTAG_RUN_RE.sub("", s)
    s = _LONE_HASHTAG_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip(" \t\n-—|·•")
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars].rsplit(" ", 1)[0].rstrip(",.;:—-·•|")
    return f"{cut}…"


def _youtube_thumb(url: str | None) -> str | None:
    """Return an mqdefault thumbnail URL for a YouTube video URL, else None.

    Only matches canonical 11-character YouTube IDs so demo placeholder URLs
    fall through to the card's solid fallback tile.
    """
    if not url:
        return None
    match = _YT_ID_RE.search(url)
    if not match:
        return None
    return f"https://i.ytimg.com/vi/{match.group(1)}/mqdefault.jpg"


def _timezone_label(value: datetime) -> str:
    """Return a short timezone label (e.g. 'CET', 'UTC+02:00') for a datetime.

    On Windows ``datetime.tzname()`` returns the long zone name
    ("Mitteleuropäische Sommerzeit"), which is unsuitable for a header line.
    We prefer a short alphabetic abbreviation when the platform provides one,
    otherwise fall back to a UTC offset.  ``LOCAL`` is the last resort for
    naive datetimes on platforms that report nothing.
    """
    aware = value if value.tzinfo else None
    if aware is None:
        try:
            aware = datetime.now().astimezone()
        except Exception:
            return "LOCAL"

    name = aware.tzname() or ""
    # Accept short alphabetic abbreviations like "CET", "CEST", "UTC", "PDT".
    if name and len(name) <= 5 and name.replace("+", "").replace("-", "").isalnum():
        return name

    offset = aware.utcoffset()
    if offset is None:
        return name or "LOCAL"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


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


def _upcoming_match_to_dict(item: CollectorItem) -> dict[str, Any]:
    """Flatten an upcoming-match CollectorItem into the template dict shape."""
    md = item.metadata or {}
    return {
        "starts_at": item.timestamp,
        "team1": md.get("team1") or "",
        "team2": md.get("team2") or "",
        "team1_logo_url": md.get("team1_logo_url"),
        "team2_logo_url": md.get("team2_logo_url"),
        "event": md.get("event"),
        "format": md.get("format"),
        "stage": md.get("stage"),
        "hltv_url": md.get("hltv_url") or item.url,
    }


def _history_entry_to_dict(entry: HistoryEntry, briefing_date: date) -> dict[str, Any]:
    """Flatten a HistoryEntry into the dict shape the template expects."""
    label_date = date(entry.year, briefing_date.month, briefing_date.day)
    return {
        "year": entry.year,
        "date_label": _fmt_date(label_date, "%B %-d, %Y"),
        "headline": entry.headline,
        "narrative": entry.narrative,
        "visual_label": entry.visual_label,
        "source_url": entry.source_url,
    }


def render_briefing(
    digest: DigestOutput,
    briefing_date: date,
    *,
    social_items: list[CollectorItem] | None = None,
    upcoming_items: list[CollectorItem] | None = None,
    this_day: HistoryEntry | None = None,
) -> str:
    """Render the briefing template to an HTML string.

    Args:
        digest: Editorial digest content grouped into briefing sections.
        briefing_date: Date represented by the briefing.
        social_items: Optional social posts to include in the template context.
        upcoming_items: Optional upcoming matches to include in the template
            context.
        this_day: Optional history entry for the briefing date.

    Returns:
        Rendered briefing HTML. save_briefing() writes it to
        output/briefings/{YYYY-MM-DD}.html.
    """
    env = _make_env()
    template = env.get_template("briefing.html")
    social_posts = [_social_post_to_dict(it) for it in (social_items or [])]
    upcoming_matches = [_upcoming_match_to_dict(it) for it in (upcoming_items or [])]
    this_day_ctx = (
        _history_entry_to_dict(this_day, briefing_date) if this_day is not None else None
    )
    blocks = _build_blocks(digest, social_posts, upcoming_matches, this_day)
    route_stops = _build_route_stops(blocks)
    generated_at = datetime.now()
    context: dict[str, Any] = {
        "digest": digest,
        "date": briefing_date,
        "generated_at": generated_at,
        "tz_label": _timezone_label(generated_at),
        "issue_no": _compute_issue_number(briefing_date),
        "ticker_chips": _build_ticker_chips(digest),
        "sources": _collect_sources(digest),
        "social_posts": social_posts,
        "upcoming_matches": upcoming_matches,
        "this_day": this_day_ctx,
        "blocks": blocks,
        "route_stops": route_stops,
        "section_limits": _SECTION_LIMITS,
        "DATE_FMT_HEADER": _DATE_FMT_HEADER,
        "DATE_FMT_FOOTER": _DATE_FMT_FOOTER,
        "DATE_FMT_TIME": _DATE_FMT_TIME,
        "per_match_blurbs": {
            url: blurb.model_dump() for url, blurb in digest.per_match_blurbs.items()
        },
    }
    return template.render(**context)


def save_briefing(html: str, briefing_date: date) -> Path:
    """Write rendered briefing HTML to the static output directory.

    Args:
        html: Rendered briefing HTML.
        briefing_date: Date used for the output filename.

    Returns:
        Path to output/briefings/{YYYY-MM-DD}.html.
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"{briefing_date.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return path
