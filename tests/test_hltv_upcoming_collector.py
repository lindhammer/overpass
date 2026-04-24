"""Tests for HLTVUpcomingCollector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from overpass.config import AppConfig, HLTVConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


_RANKINGS_HTML = """
<html><body>
<div class="ranking">
  <div class="ranked-team">
    <div class="teamLine">
      <span class="position">#1</span>
      <a class="moreLink" href="/team/9565/vitality">Vitality</a>
    </div>
  </div>
  <div class="ranked-team">
    <div class="teamLine">
      <span class="position">#2</span>
      <a class="moreLink" href="/team/4608/spirit">Spirit</a>
    </div>
  </div>
</body></html>
"""


class FakeUpcomingBrowserClient:
    def __init__(
        self,
        responses: dict[str, str | Exception],
        *,
        headless: bool = True,
        base_url: str = "https://www.hltv.org",
    ) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.wait_until_calls: list[str] = []
        self.closed = False
        self.headless = headless
        self.base_url = base_url

    async def fetch_page_content(self, path_or_url: str, wait_until: str = "domcontentloaded") -> str:
        self.calls.append(path_or_url)
        self.wait_until_calls.append(wait_until)
        response = self.responses[path_or_url]
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_collector_filters_to_watchlist_and_top_ranked_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_upcoming as upcoming_module

    browser_client = FakeUpcomingBrowserClient(
        {
            "/matches": _read_fixture("hltv_matches_upcoming.html"),
            "/ranking/teams/": _RANKINGS_HTML,
        },
        headless=False,
    )

    monkeypatch.setattr(
        upcoming_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Vitality"],
            hltv_top_n=2,
            hltv=HLTVConfig(upcoming_lookahead_hours=24, upcoming_max_matches=10),
        ),
        raising=False,
    )

    # Fixture's big-team matches (Vitality, Astralis vs G2, NaVi vs FaZe) start
    # 2026-04-29 between 15:00 and 20:00 UTC; pin "now" so they fit in 24h.
    fixed_now = datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc)
    collector = upcoming_module.HLTVUpcomingCollector(
        browser_client=browser_client,
        now=lambda: fixed_now,
    )

    items = await collector.collect()

    # Both /matches and /ranking/teams/ should have been fetched.
    assert "/matches" in browser_client.calls
    assert "/ranking/teams/" in browser_client.calls

    # Every returned item should involve a watchlist or top-N ranked team.
    relevant = {"Vitality", "Spirit"}
    assert items, "expected at least one watchlist/ranked match in the fixture window"
    for it in items:
        teams = {it.metadata["team1"], it.metadata["team2"]}
        assert teams & relevant, teams
        assert it.source == "hltv"
        assert it.type == "upcoming"
        assert it.url.startswith("https://www.hltv.org/matches/")
        assert it.timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_collector_returns_empty_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from overpass.collectors import hltv_upcoming as upcoming_module

    browser_client = FakeUpcomingBrowserClient({})
    monkeypatch.setattr(
        upcoming_module,
        "load_config",
        lambda: AppConfig(hltv=HLTVConfig(upcoming_enabled=False)),
        raising=False,
    )

    collector = upcoming_module.HLTVUpcomingCollector(browser_client=browser_client)
    items = await collector.collect()

    assert items == []
    assert browser_client.calls == []


@pytest.mark.asyncio
async def test_collector_filters_out_matches_outside_lookahead_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_upcoming as upcoming_module

    browser_client = FakeUpcomingBrowserClient(
        {
            "/matches": _read_fixture("hltv_matches_upcoming.html"),
            "/ranking/teams/": _RANKINGS_HTML,
        }
    )
    monkeypatch.setattr(
        upcoming_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Vitality"],
            hltv_top_n=2,
            hltv=HLTVConfig(upcoming_lookahead_hours=1, upcoming_max_matches=10),
        ),
        raising=False,
    )

    # Pin "now" to a time when fixture matches are still days out — window
    # of 1h means nothing should match.
    collector = upcoming_module.HLTVUpcomingCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc),
    )
    items = await collector.collect()
    assert items == []


@pytest.mark.asyncio
async def test_collector_caps_results_at_max_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    from overpass.collectors import hltv_upcoming as upcoming_module

    browser_client = FakeUpcomingBrowserClient(
        {
            "/matches": _read_fixture("hltv_matches_upcoming.html"),
            "/ranking/teams/": _RANKINGS_HTML,
        },
        headless=False,
    )
    monkeypatch.setattr(
        upcoming_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=[],
            hltv_top_n=2,
            hltv=HLTVConfig(upcoming_lookahead_hours=72, upcoming_max_matches=2),
        ),
        raising=False,
    )

    collector = upcoming_module.HLTVUpcomingCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 29, 0, 0, tzinfo=timezone.utc),
    )
    items = await collector.collect()
    assert len(items) <= 2


@pytest.mark.asyncio
async def test_collector_falls_back_to_load_when_first_fetch_returns_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If /matches returns a Cloudflare challenge, retry with wait_until='load'."""
    from overpass.collectors import hltv_upcoming as upcoming_module

    challenge_html = "<html><head><title>Just a moment...</title></head><body>cf-challenge</body></html>"

    class SequencedClient(FakeUpcomingBrowserClient):
        def __init__(self) -> None:
            super().__init__({"/ranking/teams/": _RANKINGS_HTML}, headless=False)
            self._matches_responses = [challenge_html, _read_fixture("hltv_matches_upcoming.html")]

        async def fetch_page_content(self, path_or_url, wait_until="domcontentloaded"):
            self.calls.append(path_or_url)
            self.wait_until_calls.append(wait_until)
            if path_or_url == "/matches":
                return self._matches_responses.pop(0)
            return self.responses[path_or_url]

    browser_client = SequencedClient()
    monkeypatch.setattr(
        upcoming_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Vitality"],
            hltv_top_n=0,
            hltv=HLTVConfig(upcoming_lookahead_hours=24, upcoming_max_matches=5),
        ),
        raising=False,
    )

    collector = upcoming_module.HLTVUpcomingCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc),
    )
    items = await collector.collect()

    # First /matches call domcontentloaded → challenge, second /matches with load → real HTML
    matches_calls = [(c, w) for c, w in zip(browser_client.calls, browser_client.wait_until_calls) if c == "/matches"]
    assert matches_calls[0] == ("/matches", "domcontentloaded")
    assert matches_calls[1] == ("/matches", "load")
    assert items, "expected matches after fallback recovery"
