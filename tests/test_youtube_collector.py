"""Tests for the YouTube collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from overpass.collectors.youtube import YouTubeCollector

# ── Helpers ──────────────────────────────────────────────────────

_NOW_UTC = datetime.now(tz=timezone.utc)
_RECENT_ISO = (_NOW_UTC - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
_OLD_ISO = (_NOW_UTC - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_playlist_response(items: list[dict]) -> dict:
    return {"items": items}


def _make_video_entry(
    video_id: str = "abc123",
    title: str = "Test Video",
    published_at: str = _RECENT_ISO,
    description: str = "Short description",
    thumbnails: dict | None = None,
) -> dict:
    if thumbnails is None:
        thumbnails = {
            "default": {"url": "https://i.ytimg.com/vi/abc123/default.jpg"},
            "medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"},
            "high": {"url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg"},
        }
    return {
        "snippet": {
            "publishedAt": published_at,
            "title": title,
            "description": description,
            "thumbnails": thumbnails,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }


SAMPLE_RESPONSE = _make_playlist_response([
    _make_video_entry(video_id="v1", title="Recent Upload"),
    _make_video_entry(video_id="v2", title="Old Upload", published_at=_OLD_ISO),
    _make_video_entry(video_id="v3", title="Another Recent", published_at=_RECENT_ISO),
])

EMPTY_RESPONSE = _make_playlist_response([])


def _mock_config(api_key: str = "test-key", channels: list | None = None):
    """Build a mock config with YouTube settings."""
    from overpass.config import YouTubeConfig, YoutubeChannel

    if channels is None:
        channels = [YoutubeChannel(id="UCtest123", name="TestChannel")]
    yt = YouTubeConfig(api_key_env=api_key, channels=channels)
    cfg = MagicMock()
    cfg.youtube = yt
    return cfg


def _mock_httpx_response(data: dict):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ── Tests ────────────────────────────────────────────────────────


class TestUploadsPlaylistId:
    def test_uc_prefix_replaced(self):
        assert YouTubeCollector._uploads_playlist_id("UC_SgBkrOEFVnJkBMKcpp5lg") == "UU_SgBkrOEFVnJkBMKcpp5lg"

    def test_non_uc_prefix_unchanged(self):
        assert YouTubeCollector._uploads_playlist_id("PLtest123") == "PLtest123"


class TestBestThumbnail:
    def test_picks_maxres_first(self):
        thumbnails = {
            "default": {"url": "http://d.jpg"},
            "high": {"url": "http://h.jpg"},
            "maxres": {"url": "http://m.jpg"},
        }
        assert YouTubeCollector._best_thumbnail(thumbnails) == "http://m.jpg"

    def test_falls_back_to_high(self):
        thumbnails = {
            "default": {"url": "http://d.jpg"},
            "high": {"url": "http://h.jpg"},
        }
        assert YouTubeCollector._best_thumbnail(thumbnails) == "http://h.jpg"

    def test_falls_back_to_default(self):
        thumbnails = {"default": {"url": "http://d.jpg"}}
        assert YouTubeCollector._best_thumbnail(thumbnails) == "http://d.jpg"

    def test_empty_returns_none(self):
        assert YouTubeCollector._best_thumbnail({}) is None


@pytest.mark.asyncio
async def test_recent_videos_collected():
    """Recent videos are returned, old ones filtered out."""
    cfg = _mock_config()
    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_httpx_response(SAMPLE_RESPONSE)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        collector = YouTubeCollector()
        items = await collector.collect()

    assert len(items) == 2
    titles = {i.title for i in items}
    assert "Recent Upload" in titles
    assert "Another Recent" in titles
    assert "Old Upload" not in titles


@pytest.mark.asyncio
async def test_collector_item_fields():
    """Verify all CollectorItem fields are set correctly."""
    cfg = _mock_config()
    single_response = _make_playlist_response([
        _make_video_entry(
            video_id="xyz789",
            title="CS2 Major Highlights",
            description="A" * 300,
        ),
    ])

    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_httpx_response(single_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        items = await YouTubeCollector().collect()

    assert len(items) == 1
    item = items[0]
    assert item.source == "youtube"
    assert item.type == "video"
    assert item.title == "CS2 Major Highlights"
    assert item.url == "https://www.youtube.com/watch?v=xyz789"
    assert item.thumbnail_url == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    assert item.metadata["channel_name"] == "TestChannel"
    assert item.metadata["channel_id"] == "UCtest123"
    assert item.metadata["video_id"] == "xyz789"
    assert len(item.metadata["description"]) == 200


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list():
    """An API response with no items returns an empty list."""
    cfg = _mock_config()
    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_httpx_response(EMPTY_RESPONSE)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        items = await YouTubeCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_no_api_key_skips_collection():
    """When the API key is empty, collection is skipped."""
    cfg = _mock_config(api_key="")
    with patch("overpass.collectors.youtube.load_config", return_value=cfg):
        items = await YouTubeCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_no_channels_configured():
    """When no channels are configured, returns empty list."""
    cfg = _mock_config(channels=[])
    with patch("overpass.collectors.youtube.load_config", return_value=cfg):
        items = await YouTubeCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_api_error_returns_empty_list():
    """When the API call fails, the collector returns [] for that channel."""
    cfg = _mock_config()
    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("API quota exceeded")
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        items = await YouTubeCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_quota_logging(caplog):
    """Verify quota usage is logged."""
    import logging

    cfg = _mock_config()
    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_httpx_response(SAMPLE_RESPONSE)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with caplog.at_level(logging.INFO, logger="overpass.collectors.youtube"):
            await YouTubeCollector().collect()

    assert any("quota" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_multiple_channels():
    """Videos from multiple channels are all collected."""
    from overpass.config import YoutubeChannel

    channels = [
        YoutubeChannel(id="UCchannel1", name="Channel One"),
        YoutubeChannel(id="UCchannel2", name="Channel Two"),
    ]
    cfg = _mock_config(channels=channels)

    resp1 = _make_playlist_response([_make_video_entry(video_id="v1", title="From Ch1")])
    resp2 = _make_playlist_response([_make_video_entry(video_id="v2", title="From Ch2")])

    with patch("overpass.collectors.youtube.load_config", return_value=cfg), \
         patch("overpass.collectors.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            _mock_httpx_response(resp1),
            _mock_httpx_response(resp2),
        ]
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        items = await YouTubeCollector().collect()

    assert len(items) == 2
    assert {i.metadata["channel_name"] for i in items} == {"Channel One", "Channel Two"}
