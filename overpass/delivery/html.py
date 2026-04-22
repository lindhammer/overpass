"""HTML briefing renderer – renders Jinja2 template and saves to disk."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from overpass.editorial.digest import DigestOutput

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "briefings"

# Section render order: HLTV match/news coverage ahead of the older media sections.
SECTION_ORDER = ["Matches", "News", "Clips", "Videos", "Podcasts", "Patches"]

# Matches BBCode tags like [b], [/b], [h1], [list], [*], [url=...], etc.
_BBCODE_RE = re.compile(r"\[/?[a-zA-Z0-9]+(?:=[^\]]+)?\]")


def _first_paragraph(text: str, max_chars: int = 300) -> str:
    """Strip BBCode markup and return the first non-empty paragraph."""
    clean = _BBCODE_RE.sub("", text).strip()
    for sep in ("\n\n", "\n"):
        parts = [p.strip() for p in clean.split(sep) if p.strip()]
        if parts:
            first = parts[0]
            return first if len(first) <= max_chars else first[:max_chars].rstrip() + "…"
    return clean[:max_chars].rstrip() + ("…" if len(clean) > max_chars else "")


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["first_paragraph"] = _first_paragraph
    return env


def render_briefing(digest: DigestOutput, briefing_date: date) -> str:
    """Render the briefing template and return the HTML string."""
    env = _make_env()
    template = env.get_template("briefing.html")
    return template.render(
        digest=digest,
        date=briefing_date,
        generated_at=datetime.now(),
        section_order=SECTION_ORDER,
    )


def save_briefing(html: str, briefing_date: date) -> Path:
    """Write the rendered HTML to output/briefings/{date}.html and return its path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"{briefing_date.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return path
