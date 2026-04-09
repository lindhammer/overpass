"""Tests for the Podcast collector."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from overpass.collectors.podcast import PodcastCollector

# ── Realistic RSS feed snippet ───────────────────────────────────

_NOW_UTC = datetime.now(tz=timezone.utc)
_RECENT_DATE = _NOW_UTC - timedelta(hours=6)
_OLD_DATE = _NOW_UTC - timedelta(hours=48)

_RECENT_RFC2822 = _RECENT_DATE.strftime("%a, %d %b %Y %H:%M:%S +0000")
_OLD_RFC2822 = _OLD_DATE.strftime("%a, %d %b %Y %H:%M:%S +0000")

SAMPLE_RSS = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>HLTV Confirmed</title>
    <link>https://www.hltv.org</link>
    <itunes:image href="https://img.hltv.org/podcast-cover.jpg"/>
    <item>
      <title>Episode 99 – Grand Final Preview</title>
      <link>https://example.com/ep99</link>
      <pubDate>{_RECENT_RFC2822}</pubDate>
      <itunes:duration>01:12:34</itunes:duration>
      <description>Preview of the upcoming grand final.</description>
      <itunes:image href="https://img.hltv.org/ep99.jpg"/>
    </item>
    <item>
      <title>Episode 98 – Old News</title>
      <link>https://example.com/ep98</link>
      <pubDate>{_OLD_RFC2822}</pubDate>
      <itunes:duration>00:55:10</itunes:duration>
      <description>This episode is older than 24 hours.</description>
    </item>
  </channel>
</rss>
"""

EMPTY_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>
"""


# ── Helpers ──────────────────────────────────────────────────────

def _make_config_with_feeds(feeds: list[dict]):
    """Return a minimal AppConfig-like object with podcast entries."""
    from overpass.config import AppConfig, Podcast

    return AppConfig(
        podcasts=[Podcast(**f) for f in feeds],
        telegram={"bot_token_env": "", "chat_id_env": ""},
    )


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recent_episode_collected():
    """Episodes published within the last 24 h are returned."""
    cfg = _make_config_with_feeds(
        [{"name": "HLTV Confirmed", "feed_url": "https://fake/feed.xml"}]
    )
    parsed = _parsed_feed(SAMPLE_RSS)
    with (
        patch("overpass.collectors.podcast.load_config", return_value=cfg),
        patch("overpass.collectors.podcast.feedparser.parse", return_value=parsed),
    ):
        collector = PodcastCollector()
        items = await collector.collect()

    assert len(items) == 1
    item = items[0]
    assert item.source == "podcast"
    assert item.type == "episode"
    assert item.title == "Episode 99 – Grand Final Preview"
    assert item.url == "https://example.com/ep99"
    assert item.metadata["podcast_name"] == "HLTV Confirmed"
    assert item.metadata["duration"] == "01:12:34"
    assert "Preview" in item.metadata["description"]


@pytest.mark.asyncio
async def test_old_episodes_filtered_out():
    """Episodes older than 24 h are excluded."""
    cfg = _make_config_with_feeds(
        [{"name": "Test Pod", "feed_url": "https://fake/feed.xml"}]
    )
    parsed = _parsed_feed(SAMPLE_RSS)
    with (
        patch("overpass.collectors.podcast.load_config", return_value=cfg),
        patch("overpass.collectors.podcast.feedparser.parse", return_value=parsed),
    ):
        items = await PodcastCollector().collect()

    titles = [i.title for i in items]
    assert "Episode 98 – Old News" not in titles


@pytest.mark.asyncio
async def test_empty_feed_returns_empty_list():
    """A feed with no entries produces an empty list."""
    cfg = _make_config_with_feeds(
        [{"name": "Empty Pod", "feed_url": "https://fake/empty.xml"}]
    )
    parsed = _parsed_feed(EMPTY_RSS)
    with (
        patch("overpass.collectors.podcast.load_config", return_value=cfg),
        patch("overpass.collectors.podcast.feedparser.parse", return_value=parsed),
    ):
        items = await PodcastCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_unreachable_feed_returns_empty_list():
    """When the feed raises an exception, the collector logs and returns []."""
    cfg = _make_config_with_feeds(
        [{"name": "Broken", "feed_url": "https://fake/broken.xml"}]
    )
    with (
        patch("overpass.collectors.podcast.load_config", return_value=cfg),
        patch(
            "overpass.collectors.podcast.feedparser.parse",
            side_effect=Exception("network error"),
        ),
    ):
        items = await PodcastCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_thumbnail_url_extracted():
    """Artwork URL is extracted from the feed."""
    cfg = _make_config_with_feeds(
        [{"name": "Art Pod", "feed_url": "https://fake/feed.xml"}]
    )
    parsed = _parsed_feed(SAMPLE_RSS)
    with (
        patch("overpass.collectors.podcast.load_config", return_value=cfg),
        patch("overpass.collectors.podcast.feedparser.parse", return_value=parsed),
    ):
        items = await PodcastCollector().collect()

    assert len(items) == 1
    assert items[0].thumbnail_url is not None
    assert "hltv.org" in items[0].thumbnail_url


# ── Utility ──────────────────────────────────────────────────────

def _parsed_feed(xml: str):
    """Parse an RSS string with feedparser (no network)."""
    import feedparser

    return feedparser.parse(xml)
