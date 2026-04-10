"""YouTube collector – fetches recent uploads from tracked channels via Data API v3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(BaseCollector):
    name = "youtube"

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        yt = config.youtube
        api_key = yt.api_key_env

        if not api_key:
            self.logger.warning("YouTube API key not set – skipping collection")
            return []

        if not yt.channels:
            self.logger.info("No YouTube channels configured")
            return []

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        items: list[CollectorItem] = []
        quota_used = 0

        async with httpx.AsyncClient(timeout=15) as client:
            for channel in yt.channels:
                try:
                    uploads_playlist_id = self._uploads_playlist_id(channel.id)
                    videos, cost = await self._fetch_recent_videos(
                        client, api_key, uploads_playlist_id, channel, cutoff,
                    )
                    items.extend(videos)
                    quota_used += cost
                except Exception:
                    self.logger.exception(
                        "Failed to fetch videos for channel %s (%s)",
                        channel.name,
                        channel.id,
                    )

        self.logger.info(
            "Collected %d youtube videos (estimated quota: %d units)",
            len(items),
            quota_used,
        )
        return items

    @staticmethod
    def _uploads_playlist_id(channel_id: str) -> str:
        """Derive the uploads playlist ID from a channel ID (UC… → UU…)."""
        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]
        return channel_id

    async def _fetch_recent_videos(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        playlist_id: str,
        channel,
        cutoff: datetime,
    ) -> tuple[list[CollectorItem], int]:
        """Fetch playlist items and return (items, quota_cost)."""
        resp = await client.get(
            f"{YOUTUBE_API_BASE}/playlistItems",
            params={
                "playlistId": playlist_id,
                "part": "snippet",
                "maxResults": 5,
                "key": api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        quota_cost = 1  # playlistItems.list = 1 unit

        items: list[CollectorItem] = []
        for entry in data.get("items", []):
            try:
                item = self._parse_entry(entry, channel, cutoff)
                if item is not None:
                    items.append(item)
            except Exception:
                self.logger.exception("Failed to parse YouTube playlist entry")

        return items, quota_cost

    @staticmethod
    def _best_thumbnail(thumbnails: dict) -> str | None:
        """Pick the highest-resolution thumbnail available."""
        for key in ("maxres", "high", "medium", "default"):
            thumb = thumbnails.get(key)
            if thumb and thumb.get("url"):
                return thumb["url"]
        return None

    @staticmethod
    def _parse_entry(entry: dict, channel, cutoff: datetime) -> CollectorItem | None:
        snippet = entry.get("snippet", {})
        published_str = snippet.get("publishedAt", "")
        if not published_str:
            return None

        timestamp = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        if timestamp < cutoff:
            return None

        resource = snippet.get("resourceId", {})
        video_id = resource.get("videoId", "")
        if not video_id:
            return None

        description = snippet.get("description", "")
        thumbnail_url = YouTubeCollector._best_thumbnail(snippet.get("thumbnails", {}))

        return CollectorItem(
            source="youtube",
            type="video",
            title=snippet.get("title", "Untitled"),
            url=f"https://www.youtube.com/watch?v={video_id}",
            timestamp=timestamp,
            thumbnail_url=thumbnail_url,
            metadata={
                "channel_name": channel.name,
                "channel_id": channel.id,
                "video_id": video_id,
                "description": description[:200],
            },
        )
