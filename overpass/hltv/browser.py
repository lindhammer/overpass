"""Shared Playwright-backed browser client for HLTV scraping."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin

from overpass.config import HLTVConfig, load_config


def _async_playwright_factory() -> Any:
    from playwright.async_api import async_playwright

    return async_playwright()


class HLTVBrowserClient:
    """Small reusable browser client for HLTV collectors."""

    def __init__(
        self,
        base_url: str,
        headless: bool,
        request_timeout_seconds: int,
        min_request_interval_seconds: float,
        playwright_factory: Callable[[], Any] = _async_playwright_factory,
        sleep: Callable[[float], Any] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.request_timeout_seconds = request_timeout_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self._playwright_factory = playwright_factory
        self._sleep = sleep
        self._monotonic = monotonic
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None
        self._last_request_started_at: float | None = None
        self._last_request_finished_at: float | None = None
        self._startup_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: HLTVConfig | None = None) -> HLTVBrowserClient:
        hltv_config = config or load_config().hltv
        return cls(
            base_url=hltv_config.base_url,
            headless=hltv_config.headless,
            request_timeout_seconds=hltv_config.request_timeout_seconds,
            min_request_interval_seconds=hltv_config.min_request_interval_seconds,
        )

    async def startup(self) -> HLTVBrowserClient:
        async with self._startup_lock:
            if self._page is not None:
                return self

            playwright_context = self._playwright_factory()
            playwright = None
            browser = None
            page = None

            try:
                playwright = await playwright_context.start()
                browser = await playwright.chromium.launch(headless=self.headless)
                page = await browser.new_page()
            except Exception:
                if page is not None:
                    await page.close()
                if browser is not None:
                    await browser.close()
                if playwright is not None:
                    await playwright.stop()
                raise

            self._playwright = playwright
            self._browser = browser
            self._page = page
            return self

    async def close(self) -> None:
        async with self._request_lock:
            async with self._startup_lock:
                if self._page is not None:
                    await self._page.close()
                    self._page = None

                if self._browser is not None:
                    await self._browser.close()
                    self._browser = None

                if self._playwright is not None:
                    await self._playwright.stop()
                    self._playwright = None

    async def __aenter__(self) -> HLTVBrowserClient:
        return await self.startup()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return urljoin(f"{self.base_url}/", path_or_url)

    async def fetch_page_content(self, path_or_url: str) -> str:
        async with self._request_lock:
            await self.startup()
            await self._wait_for_request_slot()

            url = self.resolve_url(path_or_url)
            self._last_request_started_at = self._monotonic()

            if self._page is None:
                raise RuntimeError("Browser page is not initialized")

            try:
                await self._page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.request_timeout_seconds * 1000,
                )
                return await self._page.content()
            finally:
                self._last_request_finished_at = self._monotonic()

    async def _wait_for_request_slot(self) -> None:
        if self._last_request_finished_at is None:
            return

        elapsed = self._monotonic() - self._last_request_finished_at
        remaining = self.min_request_interval_seconds - elapsed
        if remaining <= 0:
            return

        sleep_result = self._sleep(remaining)
        if inspect.isawaitable(sleep_result):
            await sleep_result
