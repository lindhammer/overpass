from types import SimpleNamespace

import pytest

from overpass.collectors.hltv_matches import HLTVMatchesCollector


@pytest.mark.asyncio
async def test_results_page_does_not_launch_headful_browser_without_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("sys.platform", "linux")

    config = SimpleNamespace(
        hltv=SimpleNamespace(
            base_url="https://www.hltv.org",
            request_timeout_seconds=30,
            min_request_interval_seconds=0,
            watchlist_only_matches=False,
            results_pages=1,
        ),
        watchlist_teams=[],
        hltv_top_n=0,
    )
    monkeypatch.setattr("overpass.collectors.hltv_matches.load_config", lambda: config)
    monkeypatch.setattr("overpass.collectors.hltv_matches.parse_results_listing", lambda *_args, **_kwargs: [])

    def fail_if_headful_client_is_constructed(*_args, **_kwargs):
        raise AssertionError("headful browser should not be launched without a display")

    monkeypatch.setattr("overpass.collectors.hltv_matches.HLTVBrowserClient", fail_if_headful_client_is_constructed)

    class FakeBrowserClient:
        base_url = "https://www.hltv.org"
        headless = True

        async def fetch_page_content(self, _path, wait_until="domcontentloaded"):
            return "<html><title>Just a moment...</title><script src='https://challenges.cloudflare.com/x'></script></html>"

    collector = HLTVMatchesCollector(browser_client=FakeBrowserClient())

    assert await collector._collect_results_page("/results") == []
