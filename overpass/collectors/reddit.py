"""Reddit collector – fetches top clips from r/GlobalOffensive via OAuth2."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE = "https://oauth.reddit.com"


class RedditCollector(BaseCollector):
    name = "reddit"

    def __init__(self) -> None:
        super().__init__()
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        reddit_cfg = config.reddit

        if not reddit_cfg.client_id_env or not reddit_cfg.client_secret_env:
            self.logger.warning("Reddit client ID or client secret not configured – skipping collection")
            return []

        try:
            token = await self._get_access_token(reddit_cfg)
        except Exception:
            self.logger.exception("Reddit OAuth2 authentication failed")
            return []

        try:
            posts = await self._fetch_posts(reddit_cfg, token)
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

    async def _get_access_token(self, reddit_cfg) -> str:
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        client_id = reddit_cfg.client_id_env
        client_secret = reddit_cfg.client_secret_env

        if not client_id or not client_secret:
            raise ValueError("Reddit client_id or client_secret not configured")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                TOKEN_URL,
                auth=(client_id, client_secret),
                data={
                    "grant_type": "client_credentials",
                },
                headers={
                    "User-Agent": reddit_cfg.user_agent,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            raise ValueError(f"Reddit OAuth2 response missing access_token: {data}")

        expires_in = data.get("expires_in", 3600)
        self._access_token = access_token
        self._token_expires_at = now + expires_in - 60  # refresh 60s early

        self.logger.info("Reddit OAuth2 token acquired (expires in %ds)", expires_in)
        return access_token

    async def _fetch_posts(self, reddit_cfg, token: str) -> list[dict]:
        url = f"{OAUTH_BASE}/r/{reddit_cfg.subreddit}/{reddit_cfg.sort}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                params={
                    "t": reddit_cfg.time_filter,
                    "limit": reddit_cfg.limit,
                },
                headers={
                    "Authorization": f"Bearer {token}",
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
        if flair_filter and flair not in flair_filter:
            return None

        created_utc = post.get("created_utc", 0)
        timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc)

        permalink = post.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else ""

        thumbnail = post.get("thumbnail", "")
        thumbnail_url = thumbnail if thumbnail.startswith("http") else None

        # Extract media URL if available
        media_url: str | None = None
        media = post.get("media")
        if isinstance(media, dict):
            reddit_video = media.get("reddit_video")
            if isinstance(reddit_video, dict):
                media_url = reddit_video.get("fallback_url")
        if not media_url:
            media_url = post.get("url_overridden_by_dest")

        return CollectorItem(
            source="reddit",
            type="clip",
            title=post.get("title", "Untitled"),
            url=url,
            timestamp=timestamp,
            thumbnail_url=thumbnail_url,
            metadata={
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "author": post.get("author", "[deleted]"),
                "flair": flair,
                "media_url": media_url,
                "permalink": permalink,
            },
        )
