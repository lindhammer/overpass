"""Nitter-based pro-player social-post collector.

Polls a list of pro CS players' X/Twitter timelines via Nitter RSS mirrors.
Tries each configured instance in order; first success per handle wins. Falls
back to a cached RSS payload if every instance fails. Filters retweets and
replies by default and clamps the lookback window so the briefing stays fresh.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import mktime

import feedparser
import httpx

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import SocialConfig, SocialHandle, load_config

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_RETWEET_PREFIX_RE = re.compile(r"^RT by @\S+:\s*", re.IGNORECASE)
_REPLY_PREFIX_RE = re.compile(r"^R to @\S+:\s*", re.IGNORECASE)


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = _TAG_RE.sub(" ", html or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return _WS_RE.sub(" ", text).strip()


def _entry_published(entry) -> datetime | None:
    """Extract a timezone-aware datetime from a feedparser entry."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            return None
    return None


class NitterSocialCollector(BaseCollector):
    """Fetch pro-player tweets through public Nitter RSS mirrors."""

    name = "social"

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        cfg = config.social

        if not cfg.enabled:
            self.logger.info("Social collector disabled – skipping")
            return []
        if not cfg.handles:
            self.logger.info("No social handles configured – skipping")
            return []
        if not cfg.instances:
            self.logger.warning("No Nitter instances configured – skipping")
            return []

        cache_dir = Path(cfg.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        items: list[CollectorItem] = []
        async with httpx.AsyncClient(
            timeout=cfg.request_timeout_seconds,
            headers={"User-Agent": cfg.user_agent, "Accept": "application/rss+xml,*/*"},
            follow_redirects=True,
        ) as client:
            for handle_cfg in cfg.handles:
                try:
                    handle_items = await self._collect_handle(client, handle_cfg, cfg, cache_dir)
                except Exception:
                    self.logger.exception("Social collection failed for @%s", handle_cfg.handle)
                    continue
                items.extend(handle_items)

        items.sort(key=lambda i: i.timestamp, reverse=True)
        items = items[: cfg.max_total_posts]
        self.logger.info("Collected %d social posts", len(items))
        return items

    async def _collect_handle(
        self,
        client: httpx.AsyncClient,
        handle_cfg: SocialHandle,
        cfg: SocialConfig,
        cache_dir: Path,
    ) -> list[CollectorItem]:
        rss_text: str | None = None
        for instance in cfg.instances:
            url = f"https://{instance}/{handle_cfg.handle}/rss"
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                self.logger.debug("Nitter %s failed for @%s: %s", instance, handle_cfg.handle, exc)
                continue
            if resp.status_code != 200:
                self.logger.debug(
                    "Nitter %s returned %d for @%s", instance, resp.status_code, handle_cfg.handle
                )
                continue
            text = resp.text
            if "<rss" not in text and "<feed" not in text:
                self.logger.debug("Nitter %s returned non-RSS body for @%s", instance, handle_cfg.handle)
                continue
            rss_text = text
            self._write_cache(cache_dir, handle_cfg.handle, text)
            break

        if rss_text is None:
            cached = self._read_cache(cache_dir, handle_cfg.handle)
            if cached is None:
                self.logger.warning("All Nitter instances failed for @%s and no cache present", handle_cfg.handle)
                return []
            self.logger.info("Using cached RSS for @%s (all instances failed)", handle_cfg.handle)
            rss_text = cached

        return self._parse_feed(rss_text, handle_cfg, cfg)

    def _parse_feed(
        self,
        rss_text: str,
        handle_cfg: SocialHandle,
        cfg: SocialConfig,
    ) -> list[CollectorItem]:
        feed = feedparser.parse(rss_text)
        if not feed.entries:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.lookback_hours)
        results: list[CollectorItem] = []
        # Over-scan; many entries may be filtered out as RTs/replies/old.
        for entry in feed.entries[: cfg.max_per_handle * 6]:
            published = _entry_published(entry)
            if published is None or published < cutoff:
                continue

            raw_title = (entry.get("title") or "").strip()
            if cfg.skip_retweets and _RETWEET_PREFIX_RE.match(raw_title):
                continue
            if cfg.skip_replies and _REPLY_PREFIX_RE.match(raw_title):
                continue

            body_html = entry.get("summary") or entry.get("description") or ""
            body_text = _strip_html(body_html) or raw_title
            if not body_text:
                continue
            if cfg.skip_replies and body_text.startswith("@"):
                continue

            url = entry.get("link") or ""
            results.append(
                CollectorItem(
                    source="nitter",
                    type="social",
                    title=body_text[:200],
                    url=url,
                    timestamp=published,
                    metadata={
                        "handle": handle_cfg.handle,
                        "display_name": handle_cfg.display_name or handle_cfg.handle,
                        "verified": False,
                        "body": body_text,
                        "context": None,
                        "avatar_seed": handle_cfg.handle,
                        "team_color": handle_cfg.team_color,
                        "posted_at": published.isoformat(),
                    },
                )
            )
            if len(results) >= cfg.max_per_handle:
                break

        return results

    @staticmethod
    def _cache_path(cache_dir: Path, handle: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", handle)
        return cache_dir / f"{safe}.xml"

    def _write_cache(self, cache_dir: Path, handle: str, text: str) -> None:
        try:
            self._cache_path(cache_dir, handle).write_text(text, encoding="utf-8")
        except OSError:
            self.logger.debug("Could not write Nitter cache for @%s", handle, exc_info=True)

    def _read_cache(self, cache_dir: Path, handle: str) -> str | None:
        path = self._cache_path(cache_dir, handle)
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
