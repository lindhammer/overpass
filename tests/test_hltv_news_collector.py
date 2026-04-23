from __future__ import annotations

import asyncio
from collections.abc import Callable
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from overpass.config import AppConfig, HLTVConfig
from overpass.hltv.browser import HLTVBrowserClient


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, int]] = []
        self.wait_until_calls: list[str] = []
        self.closed = False
        self.response_text = "<html>ok</html>"

    async def goto(self, url: str, wait_until: str, timeout: int) -> object:
        self.goto_calls.append((url, timeout))
        self.wait_until_calls.append(wait_until)
        return FakeResponse(self.response_text)

    async def content(self) -> str:
        return "<html>ok</html>"

    async def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    async def text(self) -> str:
        return self._text


class FakeBrowser:
    def __init__(self, page: FakePage | Callable[[], FakePage]) -> None:
        self.page = page
        self.created_pages: list[FakePage] = []
        self.closed = False

    async def new_page(self) -> FakePage:
        page = self.page() if callable(self.page) else self.page
        self.created_pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.launch_calls: list[bool] = []

    async def launch(self, headless: bool) -> FakeBrowser:
        self.launch_calls.append(headless)
        return self.browser


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self, playwright: FakePlaywright) -> None:
        self.playwright = playwright

    async def start(self) -> FakePlaywright:
        return self.playwright


class BlockingPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.active_navigation = False
        self.navigation_started = asyncio.Event()
        self.release_navigation = asyncio.Event()

    async def goto(self, url: str, wait_until: str, timeout: int) -> object:
        if self.active_navigation:
            raise RuntimeError("concurrent navigation on shared page")

        self.active_navigation = True
        self.goto_calls.append((url, timeout))
        self.wait_until_calls.append(wait_until)
        self.navigation_started.set()
        await self.release_navigation.wait()
        self.active_navigation = False
        return FakeResponse(self.response_text)


class CloseAwareBlockingPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.navigation_started = asyncio.Event()
        self.release_navigation = asyncio.Event()

    async def goto(self, url: str, wait_until: str, timeout: int) -> object:
        self.navigation_started.set()
        await self.release_navigation.wait()
        if self.closed:
            raise RuntimeError("goto on closed page")
        self.goto_calls.append((url, timeout))
        self.wait_until_calls.append(wait_until)
        return FakeResponse(self.response_text)

    async def content(self) -> str:
        if self.closed:
            raise RuntimeError("content on closed page")
        return await super().content()


class FailingNewPageBrowser(FakeBrowser):
    async def new_page(self) -> FakePage:
        raise RuntimeError("new_page failed")


class FailingGotoPage(FakePage):
    async def goto(self, url: str, wait_until: str, timeout: int) -> object:
        raise RuntimeError("boom")


class FakeNewsBrowserClient:
    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses
        self.page_responses: dict[str, str | Exception] = {}
        self.response_sequences: dict[str, list[str | Exception]] = {}
        self.page_response_sequences: dict[str, list[str | Exception]] = {}
        self.calls: list[str] = []
        self.wait_until_calls: list[str] = []
        self.response_calls: list[str] = []
        self.response_wait_until_calls: list[str] = []
        self.closed = False

    async def fetch_page_content(self, path_or_url: str, wait_until: str = "domcontentloaded") -> str:
        self.calls.append(path_or_url)
        self.wait_until_calls.append(wait_until)
        response = self._resolve_response(
            path_or_url,
            sequences=self.page_response_sequences,
            responses=self.page_responses,
            fallback_responses=self.responses,
        )
        if isinstance(response, Exception):
            raise response
        return response

    async def fetch_response_text(self, path_or_url: str, wait_until: str = "commit") -> str:
        self.response_calls.append(path_or_url)
        self.response_wait_until_calls.append(wait_until)
        response = self._resolve_response(
            path_or_url,
            sequences=self.response_sequences,
            responses=self.responses,
            fallback_responses=self.responses,
        )
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self) -> None:
        self.closed = True

    @staticmethod
    def _resolve_response(
        path_or_url: str,
        sequences: dict[str, list[str | Exception]],
        responses: dict[str, str | Exception],
        fallback_responses: dict[str, str | Exception],
    ) -> str | Exception:
        sequence = sequences.get(path_or_url)
        if sequence:
            response = sequence.pop(0)
            if not sequence:
                sequences.pop(path_or_url, None)
            return response

        if path_or_url in responses:
            return responses[path_or_url]

        return fallback_responses[path_or_url]


def _fixture_text(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def _listing_html_with_old_article() -> str:
    return _fixture_text("hltv_news_listing.html").replace(
        "</div>\n  </body>",
        """
            <a class=\"article\" href=\"/news/12347/old-update\">
                <img src=\"/gallery/12347/cover.jpg\" alt=\"Old cover image\">
                <div class=\"newstext\">Old update</div>
                <div class=\"newstc\">This article is older than 24 hours.</div>
                <div class=\"newsrecent\">
                    <time datetime=\"2026-04-20T09:00:00+00:00\">09:00</time>
                </div>
            </a>
        </div>
    </body>""",
    )


@pytest.mark.asyncio
async def test_browser_client_fetches_content_with_resolved_url_and_cleanup() -> None:
    page = FakePage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    sleep_calls: list[float] = []
    timestamps = deque([10.0, 10.0, 11.0, 12.5, 12.5])

    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=2.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
        sleep=sleep_calls.append,
        monotonic=timestamps.popleft,
    )

    first_content = await client.fetch_page_content("/news/123/test-story")
    second_content = await client.fetch_page_content("https://www.hltv.org/news/456/another-story")
    await client.close()

    assert first_content == "<html>ok</html>"
    assert second_content == "<html>ok</html>"
    assert chromium.launch_calls == [True]
    assert page.goto_calls == [
        ("https://www.hltv.org/news/123/test-story", 30000),
        ("https://www.hltv.org/news/456/another-story", 30000),
    ]
    assert page.wait_until_calls == ["domcontentloaded", "domcontentloaded"]
    assert len(browser.created_pages) == 2
    assert sleep_calls == [1.0]
    assert page.closed is True
    assert browser.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_browser_client_uses_a_fresh_page_for_each_fetch() -> None:
    pages = [FakePage(), FakePage()]
    browser = FakeBrowser(lambda: pages.pop(0))
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    await client.fetch_page_content("/news/123/test-story")
    await client.fetch_page_content("/news/456/another-story")
    await client.close()

    assert [page.goto_calls for page in browser.created_pages] == [
        [("https://www.hltv.org/news/123/test-story", 30000)],
        [("https://www.hltv.org/news/456/another-story", 30000)],
    ]
    assert [page.wait_until_calls for page in browser.created_pages] == [
        ["domcontentloaded"],
        ["domcontentloaded"],
    ]
    assert all(page.closed for page in browser.created_pages)


@pytest.mark.asyncio
async def test_browser_client_allows_custom_wait_until() -> None:
    page = FakePage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    await client.fetch_page_content("/news/archive", wait_until="commit")
    await client.close()

    assert page.goto_calls == [("https://www.hltv.org/news/archive", 30000)]
    assert page.wait_until_calls == ["commit"]


@pytest.mark.asyncio
async def test_browser_client_can_return_response_text() -> None:
    page = FakePage()
    page.response_text = "<html>response</html>"
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    html = await client.fetch_response_text("/news/archive")
    await client.close()

    assert html == "<html>response</html>"
    assert page.goto_calls == [("https://www.hltv.org/news/archive", 30000)]
    assert page.wait_until_calls == ["commit"]


@pytest.mark.asyncio
async def test_browser_client_serializes_concurrent_fetches_on_shared_page() -> None:
    page = BlockingPage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)

    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    first_fetch = asyncio.create_task(client.fetch_page_content("/news/123/test-story"))
    await page.navigation_started.wait()
    second_fetch = asyncio.create_task(client.fetch_page_content("/news/456/another-story"))
    await asyncio.sleep(0)
    page.release_navigation.set()

    first_content, second_content = await asyncio.gather(first_fetch, second_fetch)
    await client.close()

    assert first_content == "<html>ok</html>"
    assert second_content == "<html>ok</html>"
    assert page.goto_calls == [
        ("https://www.hltv.org/news/123/test-story", 30000),
        ("https://www.hltv.org/news/456/another-story", 30000),
    ]


@pytest.mark.asyncio
async def test_browser_client_close_cleans_up_after_page_creation_failure() -> None:
    browser = FailingNewPageBrowser(FakePage())
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    await client.startup()

    with pytest.raises(RuntimeError, match="new_page failed"):
        await client.fetch_page_content("/news/123/test-story")

    await client.close()

    assert browser.closed is True
    assert playwright.stopped is True
    assert client._browser is None
    assert client._playwright is None


@pytest.mark.asyncio
async def test_browser_client_close_waits_for_inflight_fetch() -> None:
    page = CloseAwareBlockingPage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=0.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
    )

    fetch_task = asyncio.create_task(client.fetch_page_content("/news/test-story"))
    await page.navigation_started.wait()

    close_task = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    assert close_task.done() is False

    page.release_navigation.set()

    assert await fetch_task == "<html>ok</html>"
    await close_task

    assert page.goto_calls == [("https://www.hltv.org/news/test-story", 30000)]
    assert page.closed is True
    assert browser.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_browser_client_failed_requests_still_respect_min_interval() -> None:
    page = FailingGotoPage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)
    sleep_calls: list[float] = []
    timestamps = deque([10.0, 10.0, 10.5, 10.5, 10.5])

    client = HLTVBrowserClient(
        base_url="https://www.hltv.org",
        headless=True,
        request_timeout_seconds=30,
        min_request_interval_seconds=2.0,
        playwright_factory=lambda: FakePlaywrightStarter(playwright),
        sleep=sleep_calls.append,
        monotonic=timestamps.popleft,
    )

    for _ in range(2):
        with pytest.raises(RuntimeError, match="boom"):
            await client.fetch_page_content("/news/test-story")

    assert sleep_calls == [1.5]


@pytest.mark.asyncio
async def test_hltv_news_collector_collects_recent_articles_and_skips_broken_pages() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _listing_html_with_old_article(),
            "https://www.hltv.org/news/12345/faze-win-cologne-opener": _fixture_text("hltv_news_article.html"),
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": "<html><body>broken</body></html>",
        }
    )
    collector = HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
    ]
    assert browser_client.response_calls == [
        "/news/archive",
        "https://www.hltv.org/news/12345/faze-win-cologne-opener",
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
    ]
    assert browser_client.wait_until_calls == ["load", "load", "load"]
    assert browser_client.response_wait_until_calls == [
        "commit",
        "commit",
        "commit",
    ]
    assert len(items) == 1

    item = items[0]
    assert item.source == "hltv"
    assert item.type == "article"
    assert item.title == "FaZe win Cologne opener"
    assert item.url == "https://www.hltv.org/news/12345/faze-win-cologne-opener"
    assert item.timestamp == datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc)
    assert item.thumbnail_url == "https://www.hltv.org/gallery/12345/cover.jpg"
    assert item.metadata == {
        "external_id": "12345",
        "teaser": "Finn \"karrigan\" Andersen's side opened the event with a comfortable series win.",
        "author": "Striker",
        "body_text": (
            "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n\n"
            "Finn \"karrigan\" Andersen said the team kept its early-game protocols simple and trusted the calling in late rounds.\n\n"
            "\"We knew the veto gave us room to play our own game,\" karrigan said."
        ),
        "tags": ["CS2", "IEM Cologne"],
    }


@pytest.mark.asyncio
async def test_hltv_news_collector_leaves_injected_browser_open() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    browser_client = FakeNewsBrowserClient({"/news/archive": "<html><body></body></html>"})
    collector = HLTVNewsCollector(browser_client=cast(HLTVBrowserClient, browser_client))

    items = await collector.collect()

    assert items == []
    assert browser_client.closed is False
    assert browser_client.response_wait_until_calls == ["commit"]


@pytest.mark.asyncio
async def test_hltv_news_collector_applies_configured_news_limit_before_article_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_news as hltv_news_module

    second_article_html = (
        _fixture_text("hltv_news_article.html")
        .replace("12345", "12346")
        .replace("FaZe win Cologne opener", "Vitality lock playoff spot")
    )
    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _fixture_text("hltv_news_listing.html"),
            "https://www.hltv.org/news/12345/faze-win-cologne-opener": _fixture_text("hltv_news_article.html"),
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": second_article_html,
        }
    )
    monkeypatch.setattr(
        hltv_news_module,
        "load_config",
        lambda: AppConfig(hltv=HLTVConfig(news_limit=1)),
        raising=False,
    )
    collector = hltv_news_module.HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == []
    assert browser_client.response_calls == [
        "/news/archive",
        "https://www.hltv.org/news/12345/faze-win-cologne-opener",
    ]
    assert browser_client.response_wait_until_calls == ["commit", "commit"]
    assert len(items) == 1
    assert items[0].metadata["external_id"] == "12345"


@pytest.mark.asyncio
async def test_hltv_news_collector_falls_back_to_rendered_page_when_response_text_is_challenge() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    article_url = "https://www.hltv.org/news/12345/faze-win-cologne-opener"
    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _fixture_text("hltv_news_listing.html"),
            article_url: """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>""",
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": _fixture_text("hltv_news_article.html")
            .replace("12345", "12346")
            .replace("FaZe win Cologne opener", "Vitality lock playoff spot"),
        }
    )
    browser_client.page_responses[article_url] = _fixture_text("hltv_news_article.html")
    collector = HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.response_calls == [
        "/news/archive",
        article_url,
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
    ]
    assert browser_client.calls == [article_url]
    assert browser_client.wait_until_calls == ["load"]
    assert len(items) == 2
    assert items[0].metadata["external_id"] == "12345"


@pytest.mark.asyncio
async def test_hltv_news_collector_retries_rendered_page_when_challenge_persists() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    article_url = "https://www.hltv.org/news/12345/faze-win-cologne-opener"
    challenge_html = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>"""
    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _fixture_text("hltv_news_listing.html"),
            article_url: challenge_html,
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": _fixture_text("hltv_news_article.html")
            .replace("12345", "12346")
            .replace("FaZe win Cologne opener", "Vitality lock playoff spot"),
        }
    )
    browser_client.page_response_sequences[article_url] = [
        challenge_html,
        _fixture_text("hltv_news_article.html"),
    ]
    collector = HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [article_url, article_url]
    assert browser_client.wait_until_calls == ["load", "load"]
    assert len(items) == 2
    assert items[0].metadata["external_id"] == "12345"


@pytest.mark.asyncio
async def test_hltv_news_collector_retries_rendered_page_after_transient_invalid_html() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    article_url = "https://www.hltv.org/news/12345/faze-win-cologne-opener"
    invalid_html = "<html><head><title>Temporary error</title></head><body><div>Loading article...</div></body></html>"
    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _fixture_text("hltv_news_listing.html"),
            article_url: invalid_html,
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": _fixture_text("hltv_news_article.html")
            .replace("12345", "12346")
            .replace("FaZe win Cologne opener", "Vitality lock playoff spot"),
        }
    )
    browser_client.page_response_sequences[article_url] = [
        invalid_html,
        _fixture_text("hltv_news_article.html"),
    ]
    collector = HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [article_url, article_url]
    assert browser_client.wait_until_calls == ["load", "load"]
    assert len(items) == 2
    assert items[0].metadata["external_id"] == "12345"


@pytest.mark.asyncio
async def test_hltv_news_collector_allows_third_rendered_retry_for_challenge_pages() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector

    article_url = "https://www.hltv.org/news/12345/faze-win-cologne-opener"
    challenge_html = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>"""
    browser_client = FakeNewsBrowserClient(
        {
            "/news/archive": _fixture_text("hltv_news_listing.html"),
            article_url: challenge_html,
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": _fixture_text("hltv_news_article.html")
            .replace("12345", "12346")
            .replace("FaZe win Cologne opener", "Vitality lock playoff spot"),
        }
    )
    browser_client.page_response_sequences[article_url] = [
        challenge_html,
        challenge_html,
        _fixture_text("hltv_news_article.html"),
    ]
    collector = HLTVNewsCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [article_url, article_url, article_url]
    assert browser_client.wait_until_calls == ["load", "load", "load"]
    assert len(items) == 2
    assert items[0].metadata["external_id"] == "12345"


def test_main_registers_hltv_news_collector() -> None:
    from overpass.collectors.hltv_news import HLTVNewsCollector
    from overpass.main import COLLECTORS

    assert any(isinstance(collector, HLTVNewsCollector) for collector in COLLECTORS)


@pytest.mark.asyncio
async def test_run_collectors_shares_one_hltv_browser_client_and_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from overpass import main as main_module

    class SharedBrowserClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakeHLTVNewsCollector:
        name = "hltv_news"

        def __init__(self, browser_client: SharedBrowserClient) -> None:
            self.browser_client = browser_client

        async def collect(self) -> list[object]:
            return []

    class FakeHLTVMatchesCollector:
        name = "hltv_matches"

        def __init__(
            self,
            browser_client: SharedBrowserClient,
            liquipedia_client: object | None = None,
        ) -> None:
            self.browser_client = browser_client
            self.liquipedia_client = liquipedia_client

        async def collect(self) -> list[object]:
            return []

    class FakeCollector:
        def __init__(self, name: str) -> None:
            self.name = name

        async def collect(self) -> list[object]:
            return []

    shared_browser_client = SharedBrowserClient()

    monkeypatch.setattr(main_module, "load_config", lambda: AppConfig(), raising=False)
    monkeypatch.setattr(
        main_module,
        "HLTVBrowserClient",
        type(
            "FakeHLTVBrowserClient",
            (),
            {"from_config": staticmethod(lambda config: shared_browser_client)},
        ),
        raising=False,
    )
    monkeypatch.setattr(main_module, "HLTVNewsCollector", FakeHLTVNewsCollector, raising=False)
    monkeypatch.setattr(main_module, "HLTVMatchesCollector", FakeHLTVMatchesCollector, raising=False)
    monkeypatch.setattr(main_module, "PodcastCollector", lambda: FakeCollector("podcast"), raising=False)
    monkeypatch.setattr(main_module, "RedditCollector", lambda: FakeCollector("reddit"), raising=False)
    monkeypatch.setattr(main_module, "SteamCollector", lambda: FakeCollector("steam"), raising=False)
    monkeypatch.setattr(main_module, "YouTubeCollector", lambda: FakeCollector("youtube"), raising=False)

    collectors = main_module.build_collectors()

    assert cast(Any, collectors[0]).browser_client is shared_browser_client
    assert cast(Any, collectors[1]).browser_client is shared_browser_client

    await main_module.run_collectors()

    assert shared_browser_client.closed is True


def test_digest_exposes_news_section_name_for_article_items() -> None:
    from overpass.editorial.digest import SECTION_NAMES

    assert SECTION_NAMES["article"] == "News"
