from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pytest

from overpass.config import AppConfig, HLTVConfig
from overpass.hltv.browser import HLTVBrowserClient


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_calls.append((url, timeout))

    async def content(self) -> str:
        return "<html>ok</html>"

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

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

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        if self.active_navigation:
            raise RuntimeError("concurrent navigation on shared page")

        self.active_navigation = True
        self.goto_calls.append((url, timeout))
        self.navigation_started.set()
        await self.release_navigation.wait()
        self.active_navigation = False


class CloseAwareBlockingPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.navigation_started = asyncio.Event()
        self.release_navigation = asyncio.Event()

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.navigation_started.set()
        await self.release_navigation.wait()
        if self.closed:
            raise RuntimeError("goto on closed page")
        self.goto_calls.append((url, timeout))

    async def content(self) -> str:
        if self.closed:
            raise RuntimeError("content on closed page")
        return await super().content()


class FailingNewPageBrowser(FakeBrowser):
    async def new_page(self) -> FakePage:
        raise RuntimeError("new_page failed")


class FailingGotoPage(FakePage):
    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        raise RuntimeError("boom")


class FakeNewsBrowserClient:
        def __init__(self, responses: dict[str, str | Exception]) -> None:
                self.responses = responses
                self.calls: list[str] = []
                self.closed = False

        async def fetch_page_content(self, path_or_url: str) -> str:
                self.calls.append(path_or_url)
                response = self.responses[path_or_url]
                if isinstance(response, Exception):
                        raise response
                return response

        async def close(self) -> None:
                self.closed = True


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
    assert sleep_calls == [1.0]
    assert page.closed is True
    assert browser.closed is True
    assert playwright.stopped is True


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
async def test_browser_client_startup_cleans_up_partial_resources_on_failure() -> None:
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

    with pytest.raises(RuntimeError, match="new_page failed"):
        await client.startup()

    assert browser.closed is True
    assert playwright.stopped is True
    assert client._playwright is None
    assert client._browser is None
    assert client._page is None


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
            "/news": _listing_html_with_old_article(),
            "https://www.hltv.org/news/12345/faze-win-cologne-opener": _fixture_text("hltv_news_article.html"),
            "https://www.hltv.org/news/12346/vitality-lock-playoff-spot": "<html><body>broken</body></html>",
        }
    )
    collector = HLTVNewsCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/news",
        "https://www.hltv.org/news/12345/faze-win-cologne-opener",
        "https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
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

    browser_client = FakeNewsBrowserClient({"/news": "<html><body></body></html>"})
    collector = HLTVNewsCollector(browser_client=browser_client)

    items = await collector.collect()

    assert items == []
    assert browser_client.closed is False


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
            "/news": _fixture_text("hltv_news_listing.html"),
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
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/news",
        "https://www.hltv.org/news/12345/faze-win-cologne-opener",
    ]
    assert len(items) == 1
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

        def __init__(self, browser_client: SharedBrowserClient) -> None:
            self.browser_client = browser_client

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

    assert collectors[0].browser_client is shared_browser_client
    assert collectors[1].browser_client is shared_browser_client

    await main_module.run_collectors()

    assert shared_browser_client.closed is True


def test_digest_exposes_news_section_name_for_article_items() -> None:
    from overpass.editorial.digest import SECTION_NAMES

    assert SECTION_NAMES["article"] == "News"
