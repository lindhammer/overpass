"""Tests for the Steam patch notes collector."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from overpass.collectors.steam import SteamCollector

# ── Sample API responses ─────────────────────────────────────────

_NOW_UTC = datetime.now(tz=timezone.utc)
_RECENT_TS = int((_NOW_UTC - timedelta(hours=3)).timestamp())
_OLD_TS = int((_NOW_UTC - timedelta(hours=48)).timestamp())

SAMPLE_RESPONSE = {
    "appnews": {
        "appid": 730,
        "newsitems": [
            {
                "gid": "1001",
                "title": "Release Notes for 4/8/2026",
                "url": "https://store.steampowered.com/news/app/730/view/1001",
                "author": "Valve",
                "contents": "[MISC]\n- Fixed a bug with smoke grenades.",
                "feedlabel": "Community Announcements",
                "date": _RECENT_TS,
                "feedname": "steam_community_announcements",
                "feed_type": 1,
                "tags": ["patchnotes"],
            },
            {
                "gid": "1002",
                "title": "Steam Blog Post",
                "url": "https://store.steampowered.com/news/app/730/view/1002",
                "author": "community_member",
                "contents": "Check out my workshop map!",
                "feedlabel": "Community",
                "date": _RECENT_TS,
                "feedname": "steam_community",
                "feed_type": 0,
                "tags": [],
            },
            {
                "gid": "1003",
                "title": "Old Patch Notes",
                "url": "https://store.steampowered.com/news/app/730/view/1003",
                "author": "Valve",
                "contents": "Old update.",
                "feedlabel": "Updates",
                "date": _OLD_TS,
                "feedname": "steam_updates",
                "feed_type": 1,
                "tags": ["patchnotes"],
            },
        ],
    }
}

EMPTY_RESPONSE = {"appnews": {"appid": 730, "newsitems": []}}


# ── Helpers ──────────────────────────────────────────────────────


def _mock_fetch(response_data: dict) -> AsyncMock:
    """Create a mock for SteamCollector._fetch_news returning the given data."""
    mock = AsyncMock(return_value=response_data)
    return mock


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recent_official_patch_collected():
    """Recent official Valve posts are returned as patch items."""
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(SAMPLE_RESPONSE)):
        collector = SteamCollector()
        items = await collector.collect()

    assert len(items) == 1
    item = items[0]
    assert item.source == "steam"
    assert item.type == "patch"
    assert item.title == "Release Notes for 4/8/2026"
    assert "1001" in item.url
    assert item.thumbnail_url is None
    assert item.metadata["feedname"] == "steam_community_announcements"
    assert "smoke grenades" in item.metadata["contents"]
    assert item.metadata["tags"] == ["patchnotes"]


@pytest.mark.asyncio
async def test_community_posts_filtered_out():
    """Non-official feednames (e.g. steam_community) are excluded."""
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(SAMPLE_RESPONSE)):
        items = await SteamCollector().collect()

    titles = [i.title for i in items]
    assert "Steam Blog Post" not in titles


@pytest.mark.asyncio
async def test_old_entries_filtered_out():
    """Entries older than 24h are excluded even with official feedname."""
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(SAMPLE_RESPONSE)):
        items = await SteamCollector().collect()

    titles = [i.title for i in items]
    assert "Old Patch Notes" not in titles


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list():
    """An API response with no news items returns an empty list."""
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(EMPTY_RESPONSE)):
        items = await SteamCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_api_unreachable_returns_empty_list():
    """When the API call raises an exception, the collector returns []."""
    mock = AsyncMock(side_effect=Exception("connection refused"))
    with patch.object(SteamCollector, "_fetch_news", mock):
        items = await SteamCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_unexpected_format_returns_empty_list():
    """Malformed API response returns empty list without crashing."""
    bad_response = {"something": "unexpected"}
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(bad_response)):
        items = await SteamCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_steam_updates_feedname_accepted():
    """Items with feedname 'steam_updates' are also collected."""
    response = {
        "appnews": {
            "appid": 730,
            "newsitems": [
                {
                    "gid": "2001",
                    "title": "CS2 Update",
                    "url": "https://store.steampowered.com/news/app/730/view/2001",
                    "author": "Valve",
                    "contents": "Major update content.",
                    "feedlabel": "Updates",
                    "date": _RECENT_TS,
                    "feedname": "steam_updates",
                    "feed_type": 1,
                    "tags": ["patchnotes", "major"],
                },
            ],
        }
    }
    with patch.object(SteamCollector, "_fetch_news", _mock_fetch(response)):
        items = await SteamCollector().collect()

    assert len(items) == 1
    assert items[0].metadata["feedname"] == "steam_updates"
    assert items[0].metadata["tags"] == ["patchnotes", "major"]
