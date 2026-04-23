"""Steam patch notes collector – polls the Steam News API for CS2 updates."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

from overpass.collectors.base import BaseCollector, CollectorItem

STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
CS2_APP_ID = 730

OFFICIAL_FEEDNAMES = frozenset({
    "steam_community_announcements",
    "steam_updates",
})

# Steam returns BBCode-flavoured markup (`[h1]`, `[list]`, `[*]`, `[b]`, ...).
# Strip tags so the briefing template can show plain text bullet points.
_BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z0-9*]+(?:=[^\]]+)?\]")
_BULLET_RE = re.compile(r"^\s*\[\*\]\s*", re.MULTILINE)


class SteamCollector(BaseCollector):
    name = "steam"

    async def collect(self) -> list[CollectorItem]:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        try:
            data = await self._fetch_news()
        except Exception:
            self.logger.exception("Failed to fetch Steam news")
            return []

        news_items = data.get("appnews", {}).get("newsitems", [])
        if not isinstance(news_items, list):
            self.logger.warning("Unexpected Steam API response format")
            return []

        items: list[CollectorItem] = []
        for entry in news_items:
            try:
                item = self._parse_entry(entry, cutoff)
                if item is not None:
                    items.append(item)
            except Exception:
                self.logger.exception("Failed to parse Steam news entry")

        self.logger.info("Collected %d steam patch notes", len(items))
        return items

    async def _fetch_news(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                STEAM_NEWS_URL,
                params={
                    "appid": CS2_APP_ID,
                    "count": 5,
                    "maxlength": 0,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _parse_entry(entry: dict, cutoff: datetime) -> CollectorItem | None:
        feedname = entry.get("feedname", "")
        if feedname not in OFFICIAL_FEEDNAMES:
            return None

        timestamp = datetime.fromtimestamp(entry.get("date", 0), tz=timezone.utc)
        if timestamp < cutoff:
            return None

        raw_contents = entry.get("contents", "") or ""
        body_text = _bbcode_to_plain(raw_contents)

        return CollectorItem(
            source="steam",
            type="patch",
            title=entry.get("title", "Untitled"),
            url=entry.get("url", ""),
            timestamp=timestamp,
            thumbnail_url=None,
            metadata={
                "contents": raw_contents,
                "body_text": body_text,
                "feedname": feedname,
                "tags": entry.get("tags", []),
            },
        )


def _bbcode_to_plain(text: str) -> str:
    """Convert Steam's BBCode-ish markup to plain text with bullet lines."""
    if not text:
        return ""
    converted = _BULLET_RE.sub("• ", text)
    converted = _BBCODE_TAG_RE.sub("", converted)
    lines = [line.rstrip() for line in converted.splitlines()]
    cleaned: list[str] = []
    blank = 0
    for line in lines:
        if not line.strip():
            blank += 1
            if blank <= 1:
                cleaned.append("")
            continue
        blank = 0
        cleaned.append(line)
    return "\n".join(cleaned).strip()
