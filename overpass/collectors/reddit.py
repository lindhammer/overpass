"""Reddit collector - fetches top clips from r/GlobalOffensive via public JSON."""

from __future__ import annotations

import html
from datetime import datetime, timezone

import httpx

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config

REDDIT_BASE = "https://www.reddit.com"


class RedditCollector(BaseCollector):
    name = "reddit"
    _CLIP_URL_MARKERS = (
        "v.redd.it/",
        "clips.twitch.tv/",
        "twitch.tv/",
        "streamable.com/",
        "youtube.com/shorts/",
    )

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        reddit_cfg = config.reddit

        try:
            posts = await self._fetch_posts(reddit_cfg)
        except Exception:
            self.logger.exception("Failed to fetch Reddit posts")
            return []

        items: list[CollectorItem] = []
        for post in posts:
            try:
                item = self._parse_post(post, reddit_cfg.flair_filter)
                if item is not None:
                    items.append(item)
            except Exception:
                self.logger.exception("Failed to parse Reddit post")

        self.logger.info("Collected %d reddit clips", len(items))
        return items

    async def _fetch_posts(self, reddit_cfg) -> list[dict]:
        url = f"{REDDIT_BASE}/r/{reddit_cfg.subreddit}/{reddit_cfg.sort}.json"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                params={
                    "t": reddit_cfg.time_filter,
                    "limit": reddit_cfg.limit,
                },
                headers={
                    "User-Agent": reddit_cfg.user_agent,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        children = data.get("data", {}).get("children", [])
        return [child.get("data", {}) for child in children]

    @staticmethod
    def _parse_post(post: dict, flair_filter: list[str]) -> CollectorItem | None:
        flair = post.get("link_flair_text") or ""
        media_url: str | None = None
        media = post.get("media")
        if isinstance(media, dict):
            reddit_video = media.get("reddit_video")
            if isinstance(reddit_video, dict):
                media_url = reddit_video.get("fallback_url")
        if not media_url:
            media_url = post.get("url_overridden_by_dest")

        if flair_filter and flair not in flair_filter:
            post_hint = post.get("post_hint") or ""
            media_url_text = (media_url or "").lower()
            is_clip_candidate = post_hint == "hosted:video" or any(
                marker in media_url_text for marker in RedditCollector._CLIP_URL_MARKERS
            )
            if not is_clip_candidate:
                return None

        created_utc = post.get("created_utc", 0)
        timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc)

        permalink = post.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else ""

        # Reddit's JSON returns thumbnail and preview URLs HTML-escaped
        # (e.g. "&amp;" instead of "&"). Jinja2's autoescape would then
        # double-escape them at render time, producing broken images.
        # Decode here so the value stored in the digest is raw.
        thumbnail = html.unescape(post.get("thumbnail", "") or "")
        thumbnail_url = thumbnail if thumbnail.startswith("http") else None

        # Prefer a higher-resolution preview image when available; fall back
        # to the (often tiny) thumbnail otherwise.
        preview = post.get("preview")
        if isinstance(preview, dict):
            images = preview.get("images") or []
            if images and isinstance(images[0], dict):
                source = images[0].get("source")
                if isinstance(source, dict):
                    src_url = html.unescape(source.get("url") or "")
                    if src_url.startswith("http"):
                        thumbnail_url = src_url

        score = post.get("score", 0)

        return CollectorItem(
            source="reddit",
            type="clip",
            title=post.get("title", "Untitled"),
            url=url,
            timestamp=timestamp,
            thumbnail_url=thumbnail_url,
            metadata={
                "subreddit": post.get("subreddit", ""),
                "score": score,
                "upvotes": score,
                "num_comments": post.get("num_comments", 0),
                "author": post.get("author", "[deleted]"),
                "flair": flair,
                "media_url": media_url,
                "permalink": permalink,
            },
        )
