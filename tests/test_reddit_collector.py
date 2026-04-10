"""Tests for the Reddit clips collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from overpass.collectors.reddit import RedditCollector
from overpass.config import AppConfig, RedditConfig

# ── Sample data ──────────────────────────────────────────────────

_NOW_UTC = datetime.now(tz=timezone.utc)
_RECENT_TS = (_NOW_UTC - timedelta(hours=3)).timestamp()

_REDDIT_CFG = RedditConfig(
    subreddit="GlobalOffensive",
    sort="top",
    time_filter="day",
    limit=10,
    flair_filter=["Highlight", "Clip"],
    client_id_env="fake-client-id",
    client_secret_env="fake-client-secret",
    user_agent="overpass:v0.1.0 (by /u/test)",
)

_APP_CONFIG = AppConfig(
    reddit=_REDDIT_CFG,
    telegram={"bot_token_env": "", "chat_id_env": ""},
)

TOKEN_RESPONSE = {
    "access_token": "fake-token-abc123",
    "token_type": "bearer",
    "expires_in": 3600,
    "scope": "*",
}

SAMPLE_LISTING = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "insane 1v5 clutch by s1mple",
                    "permalink": "/r/GlobalOffensive/comments/abc123/insane_clutch/",
                    "created_utc": _RECENT_TS,
                    "score": 4200,
                    "num_comments": 312,
                    "author": "cs2fan99",
                    "link_flair_text": "Highlight",
                    "thumbnail": "https://b.thumbs.redditmedia.com/abc.jpg",
                    "url_overridden_by_dest": "https://clips.twitch.tv/SomeClip",
                    "media": None,
                }
            },
            {
                "data": {
                    "title": "New smoke lineup on Mirage",
                    "permalink": "/r/GlobalOffensive/comments/def456/smoke_lineup/",
                    "created_utc": _RECENT_TS,
                    "score": 800,
                    "num_comments": 45,
                    "author": "smokes_guy",
                    "link_flair_text": "Tips & Guides",
                    "thumbnail": "https://b.thumbs.redditmedia.com/def.jpg",
                    "url_overridden_by_dest": "https://i.redd.it/smoke.png",
                    "media": None,
                }
            },
            {
                "data": {
                    "title": "sick AWP ace on Inferno",
                    "permalink": "/r/GlobalOffensive/comments/ghi789/awp_ace/",
                    "created_utc": _RECENT_TS,
                    "score": 2100,
                    "num_comments": 150,
                    "author": "awp_lover",
                    "link_flair_text": "Clip",
                    "thumbnail": "self",
                    "url_overridden_by_dest": None,
                    "media": {
                        "reddit_video": {
                            "fallback_url": "https://v.redd.it/xyz/DASH_720.mp4",
                        }
                    },
                }
            },
        ]
    }
}

EMPTY_LISTING = {"data": {"children": []}}


# ── Helpers ──────────────────────────────────────────────────────


def _mock_config(cfg=_APP_CONFIG):
    return patch("overpass.collectors.reddit.load_config", return_value=cfg)


def _mock_auth(token_resp=TOKEN_RESPONSE):
    mock = AsyncMock(return_value=token_resp)
    return patch.object(RedditCollector, "_get_access_token", mock)


def _mock_fetch(listing=SAMPLE_LISTING):
    mock = AsyncMock(return_value=[c["data"] for c in listing["data"]["children"]])
    return patch.object(RedditCollector, "_fetch_posts", mock)


# ── Tests: OAuth2 authentication ─────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_token_acquired():
    """OAuth2 token is fetched and used for API requests."""
    with _mock_config(), _mock_auth() as auth_mock, _mock_fetch():
        collector = RedditCollector()
        items = await collector.collect()

    auth_mock.assert_awaited_once()
    assert len(items) > 0


@pytest.mark.asyncio
async def test_auth_failure_returns_empty_list():
    """When OAuth2 fails, the collector returns [] and logs the error."""
    failing_auth = AsyncMock(side_effect=Exception("401 Unauthorized"))
    with (
        _mock_config(),
        patch.object(RedditCollector, "_get_access_token", failing_auth),
    ):
        items = await RedditCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_token_cached_across_calls():
    """The access token is cached and not re-fetched within its lifetime."""
    collector = RedditCollector()
    collector._access_token = "cached-token"
    collector._token_expires_at = 1e12  # far future

    token = await collector._get_access_token(_REDDIT_CFG)
    assert token == "cached-token"


# ── Tests: flair filtering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_highlight_flair_collected():
    """Posts with 'Highlight' flair are included."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "insane 1v5 clutch by s1mple" in titles


@pytest.mark.asyncio
async def test_clip_flair_collected():
    """Posts with 'Clip' flair are included."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "sick AWP ace on Inferno" in titles


@pytest.mark.asyncio
async def test_non_matching_flair_filtered_out():
    """Posts with flair not in flair_filter are excluded."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "New smoke lineup on Mirage" not in titles


@pytest.mark.asyncio
async def test_flair_filter_empty_passes_all():
    """When flair_filter is empty, all posts are returned."""
    cfg_no_filter = AppConfig(
        reddit=RedditConfig(
            subreddit="GlobalOffensive",
            flair_filter=[],
            client_id_env="id",
            client_secret_env="secret",
        ),
        telegram={"bot_token_env": "", "chat_id_env": ""},
    )
    with (
        patch("overpass.collectors.reddit.load_config", return_value=cfg_no_filter),
        _mock_auth(),
        _mock_fetch(),
    ):
        items = await RedditCollector().collect()

    assert len(items) == 3


# ── Tests: CollectorItem output ──────────────────────────────────


@pytest.mark.asyncio
async def test_item_fields_correct():
    """CollectorItem has the expected source, type, and metadata."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    item = next(i for i in items if "s1mple" in i.title)
    assert item.source == "reddit"
    assert item.type == "clip"
    assert item.url == "https://www.reddit.com/r/GlobalOffensive/comments/abc123/insane_clutch/"
    assert item.thumbnail_url == "https://b.thumbs.redditmedia.com/abc.jpg"
    assert item.metadata["score"] == 4200
    assert item.metadata["num_comments"] == 312
    assert item.metadata["author"] == "cs2fan99"
    assert item.metadata["flair"] == "Highlight"
    assert item.metadata["media_url"] == "https://clips.twitch.tv/SomeClip"
    assert "/r/GlobalOffensive/comments/abc123/" in item.metadata["permalink"]


@pytest.mark.asyncio
async def test_reddit_video_media_url_extracted():
    """Media URL is extracted from reddit_video when present."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    item = next(i for i in items if "AWP" in i.title)
    assert item.metadata["media_url"] == "https://v.redd.it/xyz/DASH_720.mp4"


@pytest.mark.asyncio
async def test_self_thumbnail_ignored():
    """Thumbnail value 'self' is not used as thumbnail_url."""
    with _mock_config(), _mock_auth(), _mock_fetch():
        items = await RedditCollector().collect()

    item = next(i for i in items if "AWP" in i.title)
    assert item.thumbnail_url is None


# ── Tests: empty / error responses ───────────────────────────────


@pytest.mark.asyncio
async def test_empty_listing_returns_empty():
    """An empty listing from Reddit returns no items."""
    with _mock_config(), _mock_auth(), _mock_fetch(EMPTY_LISTING):
        items = await RedditCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_fetch_failure_returns_empty():
    """When the Reddit API call fails, the collector returns []."""
    failing_fetch = AsyncMock(side_effect=Exception("503 Service Unavailable"))
    with (
        _mock_config(),
        _mock_auth(),
        patch.object(RedditCollector, "_fetch_posts", failing_fetch),
    ):
        items = await RedditCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_malformed_post_skipped():
    """A post that raises during parsing is skipped, others still collected."""
    bad_listing = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "good post",
                        "permalink": "/r/GlobalOffensive/comments/ok/good/",
                        "created_utc": _RECENT_TS,
                        "score": 100,
                        "num_comments": 5,
                        "author": "user1",
                        "link_flair_text": "Highlight",
                        "thumbnail": "https://thumb.jpg",
                        "media": None,
                    }
                },
            ]
        }
    }
    with _mock_config(), _mock_auth(), _mock_fetch(bad_listing):
        items = await RedditCollector().collect()

    assert len(items) == 1
    assert items[0].title == "good post"
