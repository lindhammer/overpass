"""HLTV news collector backed by the shared browser client and HTML parsers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from overpass.config import load_config
from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.hltv.browser import HLTVBrowserClient
from overpass.hltv.models import HLTVNewsArticle
from overpass.hltv.news import parse_news_article, parse_news_listing


class HLTVNewsCollector(BaseCollector):
    name = "hltv_news"

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
            listing_html = await self._browser_client.fetch_page_content("/news")
            listing_items = parse_news_listing(
                listing_html,
                base_url=self._base_url,
            )
            recent_listing_items = [
                listing_item for listing_item in listing_items if listing_item.published_at >= cutoff
            ][: self._news_limit]

            items: list[CollectorItem] = []
            for listing_item in recent_listing_items:
                try:
                    article_html = await self._browser_client.fetch_page_content(listing_item.url)
                    article = parse_news_article(
                        article_html,
                        article_url=listing_item.url,
                        listing_item=listing_item,
                        base_url=self._base_url,
                    )
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
