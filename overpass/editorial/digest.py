"""Digest generator – turns raw CollectorItems into an LLM-curated digest."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from pydantic import BaseModel

from overpass.collectors.base import CollectorItem
from overpass.editorial.base import BaseLLMProvider

logger = logging.getLogger("overpass.editorial.digest")

# ── Output models ────────────────────────────────────────────────


class SectionOutput(BaseModel):
    intro: str
    items: list[CollectorItem]


class DigestOutput(BaseModel):
    summary_line: str
    sections: dict[str, SectionOutput]


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

    return _parse_llm_response(raw, groups)
