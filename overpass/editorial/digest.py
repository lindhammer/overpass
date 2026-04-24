"""Digest generator – turns raw CollectorItems into an LLM-curated digest."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from pydantic import BaseModel, Field

from overpass.collectors.base import CollectorItem
from overpass.editorial.base import BaseLLMProvider

logger = logging.getLogger("overpass.editorial.digest")

# ── Output models ────────────────────────────────────────────────


class SectionOutput(BaseModel):
    intro: str
    items: list[CollectorItem]


class MatchBlurb(BaseModel):
    """Editorial copy for a single match: a short slug + one-sentence highlight."""

    tagline: str
    highlight: str


class DigestOutput(BaseModel):
    summary_line: str
    sections: dict[str, SectionOutput]
    # Keyed by CollectorItem.url for matches.
    per_match_blurbs: dict[str, MatchBlurb] = Field(default_factory=dict)


# ── Section display names ────────────────────────────────────────

SECTION_NAMES: dict[str, str] = {
    "article": "News",
    "clip": "Clips",
    "episode": "Podcasts",
    "match": "Matches",
    "patch": "Patches",
    "video": "Videos",
}

# ── System prompt ────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a concise, well-informed CS2 journalist writing a daily briefing.
Your tone is matter-of-fact, knowledgeable, and slightly editorial – never hype,\
 never emojis, never filler.  Think HLTV news desk, not Reddit post.
You write in English."""

# ── User prompt template ─────────────────────────────────────────

_USER_PROMPT = """\
Below are today's collected CS2 items grouped by type.
Your job:

1. **summary_line** – One sentence (max ~160 chars) that captures the 2-3 most \
newsworthy points across ALL sections.  Style example:
   "Parivision fumble against MongolZ in OT, ropz earns first MVP with Vitality, \
PGL Bucharest Playoffs live"

2. **sections** – For each section key listed below, write a short intro sentence \
(1-2 sentences) that gives context for that section's items.

Return **only** valid JSON matching this schema (no markdown fences, no commentary):

{{
  "summary_line": "...",
  "sections": {{
    "<section_key>": {{
      "intro": "..."
    }}
  }}
}}

The section keys you must use: {section_keys}

--- RAW DATA ---
{items_json}
"""


# ── Match-blurbs prompts (second LLM pass) ──────────────────────

_MATCH_BLURBS_SYSTEM_PROMPT = """\
You are a concise CS2 match-desk writer.  For each match given, produce two \
short pieces of editorial copy:

- "tagline":  2-4 UPPERCASE words, no punctuation.  A wire-service slug \
that captures the shape of the result.  Examples: "OT THRILLER", \
"CLEAN SWEEP", "UPSET ALERT", "TITLE DEFENSE", "BACK ON TRACK".
- "highlight":  ONE sentence (max ~140 chars), matter-of-fact, no hype, \
no emojis.  Reference a specific player, map, or score detail when the data \
allows.  Never invent stats not present in the input.

Tone: HLTV news desk, not Reddit post.  English."""

_MATCH_BLURBS_USER_PROMPT = """\
Write blurbs for the following matches.  Return **only** valid JSON keyed by \
the match URL (no markdown fences, no commentary):

{{
  "<match_url>": {{
    "tagline": "...",
    "highlight": "..."
  }}
}}

--- MATCHES ---
{matches_json}
"""


# ── Public API ───────────────────────────────────────────────────


def _group_items(items: list[CollectorItem]) -> dict[str, list[CollectorItem]]:
    groups: dict[str, list[CollectorItem]] = defaultdict(list)
    for item in items:
        groups[item.type].append(item)
    return dict(groups)


def _build_items_json(groups: dict[str, list[CollectorItem]]) -> str:
    """Serialise grouped items to a compact JSON string for the prompt."""
    out: dict[str, list[dict]] = {}
    for type_key, items in groups.items():
        section = SECTION_NAMES.get(type_key, type_key.title())
        out[section] = [
            {
                "title": i.title,
                "url": i.url,
                "source": i.source,
                "timestamp": i.timestamp.isoformat(),
                "metadata": i.metadata,
            }
            for i in items
        ]
    return json.dumps(out, indent=2, ensure_ascii=False)


def _parse_llm_response(
    raw: str,
    groups: dict[str, list[CollectorItem]],
) -> DigestOutput:
    """Parse the LLM's JSON response into a DigestOutput, with fallback."""
    # Strip possible markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON – using fallback")
        data = {}

    summary_line: str = data.get("summary_line", "Daily CS2 briefing")
    llm_sections: dict = data.get("sections", {})

    sections: dict[str, SectionOutput] = {}
    for type_key, items in groups.items():
        section_name = SECTION_NAMES.get(type_key, type_key.title())
        section_data = llm_sections.get(section_name, {})
        intro = section_data.get("intro", "") if isinstance(section_data, dict) else ""
        sections[section_name] = SectionOutput(intro=intro, items=items)

    return DigestOutput(summary_line=summary_line, sections=sections)


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _build_match_blurbs_payload(matches: list[CollectorItem]) -> str:
    """Compact, blurb-relevant JSON describing each match."""
    payload = []
    for item in matches:
        m = item.metadata or {}
        # Trim maps and player_stats to just the fields the model needs.
        maps = [
            {
                "name": mp.get("name"),
                "team1_score": mp.get("team1_score"),
                "team2_score": mp.get("team2_score"),
                "winner": mp.get("winner_name"),
            }
            for mp in (m.get("maps") or [])
        ]
        # Top 5 player_stats by rating (descending) so the prompt stays small.
        all_stats = m.get("player_stats") or []
        top_stats = sorted(
            all_stats,
            key=lambda p: p.get("rating") or 0.0,
            reverse=True,
        )[:5]
        stats = [
            {
                "team": p.get("team_name"),
                "player": p.get("player_name"),
                "kills": p.get("kills"),
                "deaths": p.get("deaths"),
                "rating": p.get("rating"),
            }
            for p in top_stats
        ]
        payload.append({
            "url": item.url,
            "team1": m.get("team1_name"),
            "team2": m.get("team2_name"),
            "team1_score": m.get("team1_score"),
            "team2_score": m.get("team2_score"),
            "winner": m.get("winner_name"),
            "event": m.get("event_name") or m.get("event"),
            "format": m.get("format"),
            "maps": maps,
            "top_players": stats,
        })
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _parse_match_blurbs_response(
    raw: str,
    matches: list[CollectorItem],
) -> dict[str, MatchBlurb]:
    text = _strip_json_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Match-blurbs LLM returned invalid JSON – skipping blurbs")
        return {}

    if not isinstance(data, dict):
        logger.warning("Match-blurbs LLM returned non-object JSON – skipping blurbs")
        return {}

    valid_urls = {item.url for item in matches}
    blurbs: dict[str, MatchBlurb] = {}
    for url, payload in data.items():
        if url not in valid_urls or not isinstance(payload, dict):
            continue
        tagline = (payload.get("tagline") or "").strip()
        highlight = (payload.get("highlight") or "").strip()
        if not tagline and not highlight:
            continue
        blurbs[url] = MatchBlurb(
            tagline=tagline or "RESULT",
            highlight=highlight,
        )
    return blurbs


async def generate_match_blurbs(
    matches: list[CollectorItem],
    provider: BaseLLMProvider,
) -> dict[str, MatchBlurb]:
    """Second LLM pass: per-match tagline + highlight, keyed by URL."""
    if not matches:
        return {}

    matches_json = _build_match_blurbs_payload(matches)
    prompt = _MATCH_BLURBS_USER_PROMPT.format(matches_json=matches_json)

    logger.info("Sending match-blurbs prompt to LLM (%d matches)", len(matches))
    raw = await provider.generate(prompt, system=_MATCH_BLURBS_SYSTEM_PROMPT)
    logger.debug("Raw match-blurbs response:\n%s", raw)

    return _parse_match_blurbs_response(raw, matches)


async def generate_digest(
    items: list[CollectorItem],
    provider: BaseLLMProvider,
) -> DigestOutput:
    """Generate an editorial digest from raw collector items."""
    if not items:
        return DigestOutput(summary_line="No items collected today.", sections={})

    groups = _group_items(items)

    section_keys = [SECTION_NAMES.get(k, k.title()) for k in groups]
    items_json = _build_items_json(groups)

    prompt = _USER_PROMPT.format(
        section_keys=", ".join(section_keys),
        items_json=items_json,
    )

    logger.info("Sending digest prompt to LLM (%d items across %d sections)",
                len(items), len(groups))

    raw = await provider.generate(prompt, system=_SYSTEM_PROMPT)
    logger.debug("Raw LLM response:\n%s", raw)

    digest = _parse_llm_response(raw, groups)

    matches = groups.get("match", [])
    if matches:
        try:
            digest.per_match_blurbs = await generate_match_blurbs(matches, provider)
        except Exception:
            logger.exception("Per-match blurbs generation failed; continuing without")

    return digest
