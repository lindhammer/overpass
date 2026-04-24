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


# Cloudflare's interactive "Just a moment..." challenge resolves itself in a
# real browser within a few seconds. We poll for it to clear so the caller
# receives the real page content instead of the interstitial HTML.
_CHALLENGE_TITLE_MARKERS = ("just a moment", "attention required")
_CHALLENGE_BODY_MARKERS = ("challenges.cloudflare.com", "cf-browser-verification", "cf-challenge")
_CHALLENGE_CLEAR_TIMEOUT_SECONDS = 15.0
_CHALLENGE_POLL_INTERVAL_SECONDS = 0.5


class HLTVBrowserClient:
    """Manage a Playwright browser session for fragile HLTV scraping.

    HLTV markup and bot defenses change frequently, so this client deliberately
    keeps scraping behavior small, explicit, and easy to adjust.
    """

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
            if self._browser is not None:
                return self

            playwright_context = self._playwright_factory()
            playwright = None
            browser = None

            try:
                playwright = await playwright_context.start()
                browser = await playwright.chromium.launch(headless=self.headless)
            except Exception:
                if browser is not None:
                    await browser.close()
                if playwright is not None:
                    await playwright.stop()
                raise

            self._playwright = playwright
            self._browser = browser
            return self

    async def close(self) -> None:
        async with self._request_lock:
            async with self._startup_lock:
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

    async def fetch_page_content(self, path_or_url: str, wait_until: str = "domcontentloaded") -> str:
        return await self._fetch(path_or_url, wait_until=wait_until, use_response_text=False)

    async def fetch_response_text(self, path_or_url: str, wait_until: str = "commit") -> str:
        return await self._fetch(path_or_url, wait_until=wait_until, use_response_text=True)

    async def _fetch(self, path_or_url: str, wait_until: str, use_response_text: bool) -> str:
        async with self._request_lock:
            await self.startup()
            await self._wait_for_request_slot()

            url = self.resolve_url(path_or_url)
            self._last_request_started_at = self._monotonic()

            if self._browser is None:
                raise RuntimeError("Browser is not initialized")

            page = None

            try:
                page = await self._browser.new_page()
                response = await page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=self.request_timeout_seconds * 1000,
                )
                if use_response_text:
                    if response is None:
                        raise RuntimeError("Navigation did not return a response")
                    text = await response.text()
                    if _looks_like_challenge(text):
                        await self._wait_for_challenge_to_clear(page)
                        text = await page.content()
                    return text
                await self._wait_for_challenge_to_clear(page)
                return await page.content()
            finally:
                if page is not None:
                    await page.close()
                self._last_request_finished_at = self._monotonic()

    async def _wait_for_challenge_to_clear(self, page: Any) -> None:
        """Poll the page until any Cloudflare interstitial is gone.

        Returns immediately if the page does not look like a challenge. Gives
        up silently after ``_CHALLENGE_CLEAR_TIMEOUT_SECONDS``; the caller is
        responsible for handling pages that still fail to parse.
        """
        try:
            content = await page.content()
        except Exception:
            return
        if not _looks_like_challenge(content):
            return

        deadline = self._monotonic() + _CHALLENGE_CLEAR_TIMEOUT_SECONDS
        while self._monotonic() < deadline:
            sleep_result = self._sleep(_CHALLENGE_POLL_INTERVAL_SECONDS)
            if inspect.isawaitable(sleep_result):
                await sleep_result
            try:
                content = await page.content()
            except Exception:
                continue
            if not _looks_like_challenge(content):
                return

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


def _looks_like_challenge(html: str) -> bool:
    """Return True if HTML looks like a Cloudflare interstitial.

    Conservative on purpose: matches both the legacy ``<title>Just a moment``
    interstitial and the newer challenge platform markup. Lower-cased once and
    scanned for any known marker.
    """
    lowered = html.lower()
    if any(marker in lowered for marker in _CHALLENGE_BODY_MARKERS):
        return True
    title_start = lowered.find("<title>")
    if title_start == -1:
        return False
    title_end = lowered.find("</title>", title_start)
    title_text = lowered[title_start + len("<title>") : title_end if title_end != -1 else title_start + 200]
    return any(marker in title_text for marker in _CHALLENGE_TITLE_MARKERS)
