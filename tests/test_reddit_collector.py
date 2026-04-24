"""Tests for the Reddit clips collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

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
    user_agent="overpass:v0.1.0 (by /u/test)",
)

_APP_CONFIG = AppConfig(
    reddit=_REDDIT_CFG,
    telegram={"bot_token_env": "", "chat_id_env": ""},
)

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


def _mock_fetch(listing=SAMPLE_LISTING):
    mock = AsyncMock(return_value=[c["data"] for c in listing["data"]["children"]])
    return patch.object(RedditCollector, "_fetch_posts", mock)


@pytest.mark.asyncio
async def test_fetch_posts_uses_public_json_listing():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = SAMPLE_LISTING

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get.return_value = response

    with patch("overpass.collectors.reddit.httpx.AsyncClient", return_value=client):
        posts = await RedditCollector()._fetch_posts(_REDDIT_CFG)

    client.get.assert_awaited_once_with(
        "https://www.reddit.com/r/GlobalOffensive/top.json",
        params={"t": "day", "limit": 10},
        headers={"User-Agent": "overpass:v0.1.0 (by /u/test)"},
    )
    assert posts == [c["data"] for c in SAMPLE_LISTING["data"]["children"]]


@pytest.mark.asyncio
async def test_collect_without_credentials_still_fetches_posts():
    cfg = AppConfig(
        reddit=RedditConfig(
            subreddit="GlobalOffensive",
            sort="top",
            time_filter="day",
            limit=10,
            flair_filter=["Highlight", "Clip"],
            user_agent="overpass:v0.1.0 (by /u/test)",
        ),
        telegram={"bot_token_env": "", "chat_id_env": ""},
    )

    with (
        patch("overpass.collectors.reddit.load_config", return_value=cfg),
        _mock_fetch(),
    ):
        items = await RedditCollector().collect()

    assert [item.title for item in items] == [
        "insane 1v5 clutch by s1mple",
        "sick AWP ace on Inferno",
    ]


# ── Tests: flair filtering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_highlight_flair_collected():
    """Posts with 'Highlight' flair are included."""
    with _mock_config(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "insane 1v5 clutch by s1mple" in titles


@pytest.mark.asyncio
async def test_clip_flair_collected():
    """Posts with 'Clip' flair are included."""
    with _mock_config(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "sick AWP ace on Inferno" in titles


@pytest.mark.asyncio
async def test_non_matching_flair_filtered_out():
    """Posts with flair not in flair_filter are excluded."""
    with _mock_config(), _mock_fetch():
        items = await RedditCollector().collect()

    titles = [i.title for i in items]
    assert "New smoke lineup on Mirage" not in titles


@pytest.mark.asyncio
async def test_hosted_video_with_non_clip_flair_collected():
    """Hosted Reddit videos are treated as clips even if flair taxonomy changes."""
    video_listing = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "Now we got snakes on the game!",
                        "permalink": "/r/GlobalOffensive/comments/live123/snakes_on_the_game/",
                        "created_utc": _RECENT_TS,
                        "score": 1500,
                        "num_comments": 88,
                        "author": "clip_hunter",
                        "link_flair_text": "Gameplay",
                        "thumbnail": "https://b.thumbs.redditmedia.com/live.jpg",
                        "post_hint": "hosted:video",
                        "url_overridden_by_dest": "https://v.redd.it/6h448wocc0xg1",
                        "media": {
                            "reddit_video": {
                                "fallback_url": "https://v.redd.it/6h448wocc0xg1/DASH_720.mp4",
                            }
                        },
                    }
                }
            ]
        }
    }

    with _mock_config(), _mock_fetch(video_listing):
        items = await RedditCollector().collect()

    assert [item.title for item in items] == ["Now we got snakes on the game!"]


@pytest.mark.asyncio
async def test_flair_filter_empty_passes_all():
    """When flair_filter is empty, all posts are returned."""
    cfg_no_filter = AppConfig(
        reddit=RedditConfig(
            subreddit="GlobalOffensive",
            flair_filter=[],
        ),
        telegram={"bot_token_env": "", "chat_id_env": ""},
    )
    with (
        patch("overpass.collectors.reddit.load_config", return_value=cfg_no_filter),
        _mock_fetch(),
    ):
        items = await RedditCollector().collect()

    assert len(items) == 3


# ── Tests: CollectorItem output ──────────────────────────────────


@pytest.mark.asyncio
async def test_item_fields_correct():
    """CollectorItem has the expected source, type, and metadata."""
    with _mock_config(), _mock_fetch():
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
    with _mock_config(), _mock_fetch():
        items = await RedditCollector().collect()

    item = next(i for i in items if "AWP" in i.title)
    assert item.metadata["media_url"] == "https://v.redd.it/xyz/DASH_720.mp4"


@pytest.mark.asyncio
async def test_self_thumbnail_ignored():
    """Thumbnail value 'self' is not used as thumbnail_url."""
    with _mock_config(), _mock_fetch():
        items = await RedditCollector().collect()

    item = next(i for i in items if "AWP" in i.title)
    assert item.thumbnail_url is None


# ── Tests: empty / error responses ───────────────────────────────


@pytest.mark.asyncio
async def test_empty_listing_returns_empty():
    """An empty listing from Reddit returns no items."""
    with _mock_config(), _mock_fetch(EMPTY_LISTING):
        items = await RedditCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_fetch_failure_returns_empty():
    """When the Reddit API call fails, the collector returns []."""
    failing_fetch = AsyncMock(side_effect=Exception("503 Service Unavailable"))
    with (
        _mock_config(),
        patch.object(RedditCollector, "_fetch_posts", failing_fetch),
    ):
        items = await RedditCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_malformed_post_skipped():
    """A post that raises during parsing is skipped, others still collected."""
    original_parse_post = RedditCollector._parse_post

    bad_listing = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "bad post",
                        "permalink": "/r/GlobalOffensive/comments/bad123/bad/",
                        "created_utc": _RECENT_TS,
                        "score": 10,
                        "num_comments": 1,
                        "author": "broken_user",
                        "link_flair_text": "Highlight",
                        "thumbnail": "https://bad-thumb.jpg",
                        "media": None,
                    }
                },
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

    def _parse_post_side_effect(post, flair_filter):
        if post["title"] == "bad post":
            raise ValueError("malformed post")
        return original_parse_post(post, flair_filter)

    with (
        _mock_config(),
        _mock_fetch(bad_listing),
        patch.object(
            RedditCollector,
            "_parse_post",
            side_effect=_parse_post_side_effect,
        ) as mock_parse,
    ):
        items = await RedditCollector().collect()

    assert mock_parse.call_count == 2
    assert len(items) == 1
    assert items[0].title == "good post"
