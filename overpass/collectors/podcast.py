"""Podcast collector – polls RSS feeds for recent episodes."""

from __future__ import annotations

import calendar
import time
from datetime import datetime, timedelta, timezone

import feedparser

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config


class PodcastCollector(BaseCollector):
    name = "podcast"

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        items: list[CollectorItem] = []

        for podcast in config.podcasts:
            try:
                episodes = self._parse_feed(podcast.name, podcast.feed_url, cutoff)
                items.extend(episodes)
            except Exception:
                self.logger.exception("Failed to fetch feed for %s", podcast.name)

        self.logger.info("Collected %d podcast episodes", len(items))
        return items

    def _parse_feed(
        self,
        podcast_name: str,
        feed_url: str,
        cutoff: datetime,
    ) -> list[CollectorItem]:
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            self.logger.warning("Feed %s could not be parsed: %s", podcast_name, feed.bozo_exception)
            return []

        items: list[CollectorItem] = []
        for entry in feed.entries:
            published = self._parse_date(entry)
            if published is None or published < cutoff:
                continue

            thumbnail_url = self._extract_artwork(entry, feed)
            duration = entry.get("itunes_duration", "")
            description = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")

            items.append(
                CollectorItem(
                    source="podcast",
                    type="episode",
                    title=entry.get("title", "Untitled"),
                    url=link,
                    timestamp=published,
                    thumbnail_url=thumbnail_url,
                    metadata={
                        "podcast_name": podcast_name,
                        "duration": duration,
                        "description": description,
                    },
                )
            )

        return items

    @staticmethod
    def _parse_date(entry: dict) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            tp = entry.get(field)
            if tp is not None:
                try:
                    return datetime.fromtimestamp(
                        calendar.timegm(tp), tz=timezone.utc
                    )
                except (TypeError, ValueError, OverflowError):
                    continue
        return None

    @staticmethod
    def _extract_artwork(entry: dict, feed) -> str | None:
        # Entry-level itunes image
        img = entry.get("image")
        if img and isinstance(img, dict) and img.get("href"):
            return img["href"]

        # itunes_image on the entry (feedparser normalises this)
        itunes_img = entry.get("itunes_image")
        if itunes_img and isinstance(itunes_img, dict) and itunes_img.get("href"):
            return itunes_img["href"]

        # Feed-level image fallback
        feed_img = getattr(feed.feed, "image", None)
        if feed_img and isinstance(feed_img, dict) and feed_img.get("href"):
            return feed_img["href"]

        itunes_feed_img = getattr(feed.feed, "itunes_image", None)
        if itunes_feed_img and isinstance(itunes_feed_img, dict) and itunes_feed_img.get("href"):
            return itunes_feed_img["href"]

        return None
