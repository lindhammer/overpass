"""Liquipedia MediaWiki client — UA, rate-limited, cached."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from overpass.config import LiquipediaConfig
from overpass.liquipedia.cache import FileCache
from overpass.liquipedia.ratelimit import AsyncRateLimiter

logger = logging.getLogger("overpass.liquipedia.client")


class LiquipediaClient:
    """Rate-limited MediaWiki API client for Liquipedia.

    All API requests pass through the configured rate limiter and cached parse
    or search responses are reused when available. HTTP and parse failures
    soft-fail so callers receive empty results.
    """

    def __init__(
        self,
        api_url: str,
        user_agent: str,
        request_timeout_seconds: int,
        cache: FileCache,
        rate_limiter: AsyncRateLimiter,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url
        self._cache = cache
        self._rate_limiter = rate_limiter
        client_kwargs: dict = {
            "headers": {"User-Agent": user_agent},
            "timeout": request_timeout_seconds,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**client_kwargs)

    @classmethod
    def from_config(
        cls,
        cfg: LiquipediaConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "LiquipediaClient":
        """Build a client from Liquipedia configuration.

        Args:
            cfg: Liquipedia configuration with API, cache, timeout, and rate
                limit settings.
            transport: Optional httpx transport for tests or custom networking.

        Returns:
            A configured LiquipediaClient instance.
        """
        cache = FileCache(
            root=Path(cfg.cache_dir),
            ttl_seconds=cfg.cache_ttl_minutes * 60,
        )
        limiter = AsyncRateLimiter(min_interval=cfg.min_request_interval_seconds)
        return cls(
            api_url=cfg.api_url,
            user_agent=cfg.user_agent,
            request_timeout_seconds=cfg.request_timeout_seconds,
            cache=cache,
            rate_limiter=limiter,
            transport=transport,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def parse_page(self, page_title: str) -> str:
        """Fetch rendered HTML for a wiki page through the MediaWiki API.

        Args:
            page_title: Liquipedia page title to parse.

        Returns:
            Rendered page HTML, or an empty string on request or response
            parsing failure.
        """
        cache_key = f"parse:{page_title}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "action": "parse",
            "page": page_title,
            "format": "json",
            "prop": "text",
        }
        body = await self._fetch_json(params)
        if not body:
            return ""
        try:
            html = body["parse"]["text"]["*"]
        except (KeyError, TypeError):
            logger.warning("Unexpected Liquipedia parse response for %s", page_title)
            return ""
        self._cache.set(cache_key, html)
        return html

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        """Search Liquipedia page titles through MediaWiki search APIs.

        Args:
            query: Search query to send to Liquipedia.
            limit: Maximum number of titles to request.

        Returns:
            Matching page titles, or an empty list on request failure.
        """
        cache_key = f"search:v2:{query}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass

        opensearch_params = {
            "action": "opensearch",
            "search": query,
            "limit": str(limit),
            "format": "json",
        }
        body = await self._fetch_json(opensearch_params)
        titles: list[str] = []
        if isinstance(body, list) and len(body) >= 2 and isinstance(body[1], list):
            titles = [t for t in body[1] if isinstance(t, str)]

        if not titles:
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": str(limit),
                "format": "json",
            }
            body = await self._fetch_json(search_params)
            search_results = body.get("query", {}).get("search", []) if isinstance(body, dict) else []
            if isinstance(search_results, list):
                titles = [
                    item.get("title")
                    for item in search_results
                    if isinstance(item, dict) and isinstance(item.get("title"), str)
                ]

        self._cache.set(cache_key, json.dumps(titles))
        return titles

    async def _fetch_json(self, params: dict[str, str]):
        await self._rate_limiter.acquire()
        try:
            resp = await self._client.get(self._api_url, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Liquipedia request failed (%s): %s", params.get("action"), exc)
            return None
