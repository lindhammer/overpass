"""HLTV news collector backed by the shared browser client and HTML parsers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from overpass.config import load_config
from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.hltv.browser import HLTVBrowserClient, _looks_like_challenge, can_launch_headful_browser
from overpass.hltv.models import HLTVNewsArticle
from overpass.hltv.news import parse_news_article, parse_news_listing


class HLTVNewsCollector(BaseCollector):
    name = "hltv_news"
    _MAX_RENDERED_ARTICLE_ATTEMPTS = 3
    _CHALLENGE_MARKERS = (
        "<title>just a moment",
        "checking your browser before accessing",
        "cf-browser-verification",
        "cf-challenge",
        "challenges.cloudflare.com",
    )

    def __init__(
        self,
        browser_client: HLTVBrowserClient | None = None,
        now: Callable[[], datetime] | None = None,
        base_url: str = "https://www.hltv.org",
    ) -> None:
        config = load_config().hltv
        self._owns_browser_client = browser_client is None
        self._browser_client = browser_client or HLTVBrowserClient.from_config(config)
        self._base_url = getattr(
            self._browser_client,
            "base_url",
            config.base_url if self._owns_browser_client else base_url,
        ).rstrip("/")
        self._news_limit = config.news_limit
        self._now = now or (lambda: datetime.now(tz=timezone.utc))
        super().__init__()

    async def collect(self) -> list[CollectorItem]:
        cutoff = self._now() - timedelta(hours=24)

        try:
            listing_html = await self._browser_client.fetch_response_text("/news/archive")
            listing_items = parse_news_listing(
                listing_html,
                base_url=self._base_url,
            )
            recent_listing_items = [
                listing_item
                for listing_item in listing_items
                if listing_item.published_at >= cutoff or listing_item.published_at.date() >= cutoff.date()
            ][: self._news_limit]

            items: list[CollectorItem] = []
            for listing_item in recent_listing_items:
                try:
                    article = await self._collect_article(listing_item)
                except Exception:
                    self.logger.exception(
                        "Failed to collect HLTV article %s",
                        listing_item.url,
                    )
                    continue

                items.append(self._to_collector_item(article))

            self.logger.info("Collected %d HLTV news articles", len(items))
            return items
        except Exception:
            self.logger.exception("Failed to collect HLTV news")
            return []
        finally:
            if self._owns_browser_client:
                await self._browser_client.close()

    @staticmethod
    def _to_collector_item(article: HLTVNewsArticle) -> CollectorItem:
        metadata = {
            "external_id": article.external_id,
            "body_text": article.body_text or "",
            "tags": article.tags,
        }
        if article.teaser is not None:
            metadata["teaser"] = article.teaser
        if article.author is not None:
            metadata["author"] = article.author

        return CollectorItem(
            source="hltv",
            type="article",
            title=article.title,
            url=article.url,
            timestamp=article.published_at,
            thumbnail_url=article.thumbnail_url,
            metadata=metadata,
        )

    async def _collect_article(self, listing_item) -> HLTVNewsArticle:
        article_html = await self._browser_client.fetch_response_text(listing_item.url)
        if not _looks_like_challenge(article_html):
            try:
                return parse_news_article(
                    article_html,
                    article_url=listing_item.url,
                    listing_item=listing_item,
                    base_url=self._base_url,
                )
            except ValueError as first_error:
                last_error: ValueError = first_error
        else:
            self.logger.warning(
                "HLTV article %s returned a Cloudflare challenge; retrying with full render",
                listing_item.url,
            )
            last_error = ValueError("Cloudflare challenge intercepted article fetch")

        cf_blocked = _looks_like_challenge(article_html)
        for _ in range(self._MAX_RENDERED_ARTICLE_ATTEMPTS):
            rendered_article_html = await self._browser_client.fetch_page_content(
                listing_item.url,
                wait_until="load",
            )
            if _looks_like_challenge(rendered_article_html):
                cf_blocked = True
                last_error = ValueError("Cloudflare challenge persisted after rendered fetch")
                continue
            cf_blocked = False
            try:
                return parse_news_article(
                    rendered_article_html,
                    article_url=listing_item.url,
                    listing_item=listing_item,
                    base_url=self._base_url,
                )
            except ValueError as rendered_error:
                last_error = rendered_error

        # Final escalation: headless Chromium is fingerprinted as a bot by
        # Cloudflare and the JS challenge never resolves. A headful browser
        # bypasses this reliably, so it is worth the cost on the rare article
        # that triggers a challenge.
        if cf_blocked and getattr(self._browser_client, "headless", False) and can_launch_headful_browser():
            hltv_config = load_config().hltv
            headful_client = HLTVBrowserClient(
                base_url=self._base_url,
                headless=False,
                request_timeout_seconds=hltv_config.request_timeout_seconds,
                min_request_interval_seconds=hltv_config.min_request_interval_seconds,
            )
            try:
                self.logger.warning(
                    "HLTV article %s blocked by Cloudflare in headless mode; escalating to headful",
                    listing_item.url,
                )
                headful_html = await headful_client.fetch_page_content(
                    listing_item.url, wait_until="load"
                )
                if not _looks_like_challenge(headful_html):
                    return parse_news_article(
                        headful_html,
                        article_url=listing_item.url,
                        listing_item=listing_item,
                        base_url=self._base_url,
                    )
            finally:
                await headful_client.close()

        raise last_error

    @classmethod
    def _looks_like_challenge_page(cls, html: str) -> bool:
        lowered_html = html.lower()
        return any(marker in lowered_html for marker in cls._CHALLENGE_MARKERS)
