from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from overpass.config import AppConfig, HLTVConfig
from overpass.hltv.browser import HLTVBrowserClient


class FakeMatchesBrowserClient:
    def __init__(self, responses: dict[str, str | Exception], *, headless: bool = True) -> None:
        self.responses = responses
        self.response_sequences: dict[str, list[str | Exception]] = {}
        self.calls: list[str] = []
        self.wait_until_calls: list[str] = []
        self.closed = False
        self.headless = headless

    async def fetch_page_content(self, path_or_url: str, wait_until: str = "domcontentloaded") -> str:
        self.calls.append(path_or_url)
        self.wait_until_calls.append(wait_until)
        response = self._resolve_response(path_or_url)
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self) -> None:
        self.closed = True

    def _resolve_response(self, path_or_url: str) -> str | Exception:
        sequence = self.response_sequences.get(path_or_url)
        if sequence:
            response = sequence.pop(0)
            if not sequence:
                self.response_sequences.pop(path_or_url, None)
            return response

        return self.responses[path_or_url]


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _match_detail_html_for_second_listing_item() -> str:
    return (
        _read_fixture("hltv_match_detail.html")
        .replace("2412345", "2412346")
        .replace("Spirit", "Vitality")
        .replace("FaZe", "MOUZ")
    )


@pytest.mark.asyncio
async def test_hltv_matches_collector_collects_recent_matches_and_skips_broken_detail_pages() -> None:
    from overpass.collectors.hltv_matches import HLTVMatchesCollector

    browser_client = FakeMatchesBrowserClient(
        {
            "/results": _read_fixture("hltv_results.html"),
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": "<html><body>broken</body></html>",
        }
    )
    collector = HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert browser_client.wait_until_calls == [
        "domcontentloaded",
        "domcontentloaded",
        "domcontentloaded",
        "load",
    ]
    assert len(items) == 1

    item = items[0]
    assert item.source == "hltv"
    assert item.type == "match"
    assert item.title == "Spirit vs FaZe"
    assert item.url == "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026"
    assert item.timestamp == datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc)
    assert item.thumbnail_url is None
    assert item.metadata == {
        "external_id": "2412345",
        "team1_name": "Spirit",
        "team2_name": "FaZe",
        "team1_score": 2,
        "team2_score": 1,
        "winner_name": "Spirit",
        "event_name": "BLAST Open Lisbon 2026",
        "format": "bo3",
        "maps": [
            {
                "name": "Mirage",
                "team1_score": 13,
                "team2_score": 9,
                "winner_name": "Spirit",
            },
            {
                "name": "Ancient",
                "team1_score": 11,
                "team2_score": 13,
                "winner_name": "FaZe",
            },
            {
                "name": "Anubis",
                "team1_score": 13,
                "team2_score": 8,
                "winner_name": "Spirit",
            },
        ],
        "veto": [
            {
                "team_name": "Spirit",
                "action": "removed",
                "map_name": "Inferno",
            },
            {
                "team_name": "FaZe",
                "action": "removed",
                "map_name": "Nuke",
            },
            {
                "team_name": "Spirit",
                "action": "picked",
                "map_name": "Mirage",
            },
            {
                "team_name": "FaZe",
                "action": "picked",
                "map_name": "Ancient",
            },
            {
                "team_name": None,
                "action": "left_over",
                "map_name": "Anubis",
            },
        ],
        "player_stats": [
            {
                "team_name": "Spirit",
                "player_name": "donk",
                "kills": 47,
                "deaths": 30,
                "adr": 101.2,
                "kast": 78.4,
                "rating": 1.39,
            },
            {
                "team_name": "Spirit",
                "player_name": "sh1ro",
                "kills": 41,
                "deaths": 28,
                "adr": 84.3,
                "kast": 74.5,
                "rating": 1.22,
            },
            {
                "team_name": "FaZe",
                "player_name": "broky",
                "kills": 38,
                "deaths": 39,
                "adr": 77.1,
                "kast": 68.6,
                "rating": 1.03,
            },
            {
                "team_name": "FaZe",
                "player_name": "frozen",
                "kills": 31,
                "deaths": 42,
                "adr": 69.8,
                "kast": 62.7,
                "rating": 0.91,
            },
        ],
    }


@pytest.mark.asyncio
async def test_hltv_matches_collector_applies_watchlist_filter_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    browser_client = FakeMatchesBrowserClient(
        {
            "/results": _read_fixture("hltv_results.html"),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        }
    )
    monkeypatch.setattr(
        hltv_matches_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Vitality"],
            hltv=HLTVConfig(watchlist_only_matches=True),
        ),
        raising=False,
    )
    collector = hltv_matches_module.HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert len(items) == 1
    assert items[0].metadata["external_id"] == "2412346"


@pytest.mark.asyncio
async def test_hltv_matches_collector_uses_watchlist_and_top_ranked_team_relevance_when_watchlist_only_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    ranked_results_html = """
    <div class="results-all">
      <a class="a-reset" href="/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-21T18:00:00+00:00"></div>
          <div class="team team1">Spirit <span class="team-rank">#1</span></div>
          <div class="result-score"><span>2</span><span>1</span></div>
          <div class="team team2">FaZe <span class="team-rank">#7</span></div>
          <div class="map-text">bo3</div>
          <div class="event-name">BLAST Open Lisbon 2026</div>
        </div>
      </a>
      <a class="a-reset" href="/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-21T20:30:00+00:00"></div>
          <div class="team team1">Vitality</div>
          <div class="result-score"><span>2</span><span>0</span></div>
          <div class="team team2">MOUZ</div>
          <div class="map-text">bo3</div>
          <div class="event-name">BLAST Open Lisbon 2026</div>
        </div>
      </a>
      <a class="a-reset" href="/matches/2412347/furia-vs-liquid-iem-rio-2026">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-21T21:00:00+00:00"></div>
          <div class="team team1">FURIA <span class="team-rank">#12</span></div>
          <div class="result-score"><span>2</span><span>0</span></div>
          <div class="team team2">Liquid</div>
          <div class="map-text">bo3</div>
          <div class="event-name">IEM Rio 2026</div>
        </div>
      </a>
    </div>
    """
    browser_client = FakeMatchesBrowserClient(
        {
            "/results": ranked_results_html,
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        }
    )
    monkeypatch.setattr(
        hltv_matches_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Vitality"],
            hltv_top_n=5,
            hltv=HLTVConfig(watchlist_only_matches=False),
        ),
        raising=False,
    )
    collector = hltv_matches_module.HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert [item.metadata["external_id"] for item in items] == ["2412345", "2412346"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_returns_no_matches_when_rank_lookup_is_unavailable_and_watchlist_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    browser_client = FakeMatchesBrowserClient({"/results": _read_fixture("hltv_results.html")})
    async def no_rankings(_: object) -> set[str]:
        return set()

    monkeypatch.setattr(
        hltv_matches_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=[],
            hltv_top_n=5,
            hltv=HLTVConfig(watchlist_only_matches=False),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        hltv_matches_module.HLTVMatchesCollector,
        "_fetch_top_ranked_team_names_from_rankings",
        no_rankings,
        raising=False,
    )
    collector = hltv_matches_module.HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert items == []
    assert browser_client.calls == ["/results"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_uses_rankings_fallback_when_results_rows_lack_ranks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    rankless_results_html = """
    <div class="results-all">
      <a class="a-reset" href="/matches/2412348/9z-vs-alka-betboom-rush-b-summit-season-3">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-22T20:30:00+00:00"></div>
          <div class="team team1">9z</div>
          <div class="result-score"><span>2</span><span>0</span></div>
          <div class="team team2">ALKA</div>
          <div class="map-text">bo3</div>
          <div class="event-name">BetBoom Rush B Summit Season 3</div>
        </div>
      </a>
    </div>
    """
    browser_client = FakeMatchesBrowserClient(
        {
            "/results": rankless_results_html,
            "https://www.hltv.org/matches/2412348/9z-vs-alka-betboom-rush-b-summit-season-3": _read_fixture(
                "hltv_match_detail.html"
            )
            .replace("2412345", "2412348")
            .replace("Spirit", "9z")
            .replace("FaZe", "ALKA"),
        }
    )

    async def rankings(_: object) -> set[str]:
        return {"9z"}

    monkeypatch.setattr(
        hltv_matches_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=[],
            hltv_top_n=10,
            hltv=HLTVConfig(watchlist_only_matches=False),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        hltv_matches_module.HLTVMatchesCollector,
        "_fetch_top_ranked_team_names_from_rankings",
        rankings,
        raising=False,
    )
    collector = hltv_matches_module.HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 23, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "https://www.hltv.org/matches/2412348/9z-vs-alka-betboom-rush-b-summit-season-3",
    ]
    assert [item.metadata["external_id"] for item in items] == ["2412348"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_fetches_configured_number_of_results_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    second_page_results_html = """
    <div class="results-all">
      <a class="a-reset" href="/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-21T20:30:00+00:00"></div>
          <div class="team team1">Vitality</div>
          <div class="result-score"><span>2</span><span>0</span></div>
          <div class="team team2">MOUZ</div>
          <div class="map-text">bo3</div>
          <div class="event-name">BLAST Open Lisbon 2026</div>
        </div>
      </a>
    </div>
    """
    browser_client = FakeMatchesBrowserClient(
        {
            "/results": _read_fixture("hltv_results.html"),
            "/results?offset=100": second_page_results_html,
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        }
    )
    monkeypatch.setattr(
        hltv_matches_module,
        "load_config",
        lambda: AppConfig(
            watchlist_teams=["Spirit", "Vitality"],
            hltv=HLTVConfig(results_pages=2),
        ),
        raising=False,
    )
    collector = hltv_matches_module.HLTVMatchesCollector(
        browser_client=browser_client,
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "/results?offset=100",
        "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert [item.metadata["external_id"] for item in items] == ["2412345", "2412346", "2412346"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_retries_results_page_when_initial_response_is_challenge() -> None:
    from overpass.collectors.hltv_matches import HLTVMatchesCollector

    challenge_html = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>"""
    browser_client = FakeMatchesBrowserClient(
        {
            "/results": _read_fixture("hltv_results.html"),
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        }
    )
    browser_client.response_sequences["/results"] = [challenge_html, _read_fixture("hltv_results.html")]
    collector = HLTVMatchesCollector(
        browser_client=cast(HLTVBrowserClient, browser_client),
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert browser_client.calls == [
        "/results",
        "/results",
        "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert browser_client.wait_until_calls[:2] == ["domcontentloaded", "load"]
    assert [item.metadata["external_id"] for item in items] == ["2412345", "2412346"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_uses_headful_results_fallback_when_challenge_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    async def no_rankings(_: object) -> set[str]:
        return set()

    challenge_html = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>"""
    primary_client = FakeMatchesBrowserClient(
        {
            "/results": challenge_html,
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        },
        headless=True,
    )
    primary_client.response_sequences["/results"] = [challenge_html, challenge_html]
    headful_client = FakeMatchesBrowserClient(
        {"/results": _read_fixture("hltv_results.html")},
        headless=False,
    )

    class FakeHLTVBrowserClient:
        @staticmethod
        def from_config(config: HLTVConfig) -> FakeMatchesBrowserClient:
            return primary_client

        def __new__(
            cls,
            *,
            base_url: str,
            headless: bool,
            request_timeout_seconds: int,
            min_request_interval_seconds: float,
            playwright_factory: object | None = None,
            sleep: object | None = None,
            monotonic: object | None = None,
        ) -> FakeMatchesBrowserClient:
            return headful_client if not headless else primary_client

    monkeypatch.setattr(hltv_matches_module, "HLTVBrowserClient", FakeHLTVBrowserClient, raising=False)
    monkeypatch.setattr(
        hltv_matches_module.HLTVMatchesCollector,
        "_fetch_top_ranked_team_names_from_rankings",
        no_rankings,
        raising=False,
    )

    collector = hltv_matches_module.HLTVMatchesCollector(
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert primary_client.calls == [
        "/results",
        "/results",
        "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
    ]
    assert primary_client.wait_until_calls[:2] == ["domcontentloaded", "load"]
    assert headful_client.calls == ["/results"]
    assert headful_client.wait_until_calls == ["load"]
    assert headful_client.closed is True
    assert [item.metadata["external_id"] for item in items] == ["2412345", "2412346"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_retries_headful_results_fallback_with_domcontentloaded_after_load_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    async def no_rankings(_: object) -> set[str]:
        return set()

    challenge_html = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing HLTV.org</body></html>"""
    primary_client = FakeMatchesBrowserClient(
        {
            "/results": challenge_html,
            "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026": _read_fixture(
                "hltv_match_detail.html"
            ),
            "https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026": _match_detail_html_for_second_listing_item(),
        },
        headless=True,
    )
    primary_client.response_sequences["/results"] = [challenge_html, challenge_html]
    headful_client = FakeMatchesBrowserClient(
        {"/results": _read_fixture("hltv_results.html")},
        headless=False,
    )
    headful_client.response_sequences["/results"] = [
        TimeoutError("Page.goto: Timeout 30000ms exceeded."),
        _read_fixture("hltv_results.html"),
    ]

    class FakeHLTVBrowserClient:
        @staticmethod
        def from_config(config: HLTVConfig) -> FakeMatchesBrowserClient:
            return primary_client

        def __new__(
            cls,
            *,
            base_url: str,
            headless: bool,
            request_timeout_seconds: int,
            min_request_interval_seconds: float,
            playwright_factory: object | None = None,
            sleep: object | None = None,
            monotonic: object | None = None,
        ) -> FakeMatchesBrowserClient:
            return headful_client if not headless else primary_client

    monkeypatch.setattr(hltv_matches_module, "HLTVBrowserClient", FakeHLTVBrowserClient, raising=False)
    monkeypatch.setattr(
        hltv_matches_module.HLTVMatchesCollector,
        "_fetch_top_ranked_team_names_from_rankings",
        no_rankings,
        raising=False,
    )

    collector = hltv_matches_module.HLTVMatchesCollector(
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert headful_client.calls == ["/results", "/results"]
    assert headful_client.wait_until_calls == ["load", "domcontentloaded"]
    assert headful_client.closed is True
    assert [item.metadata["external_id"] for item in items] == ["2412345", "2412346"]


@pytest.mark.asyncio
async def test_hltv_matches_collector_retries_match_detail_with_headful_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from overpass.collectors import hltv_matches as hltv_matches_module

    async def no_rankings(_: object) -> set[str]:
        return set()

    detail_url = "https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026"
    single_results_html = """
    <div class="results-all">
      <a class="a-reset" href="/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026">
        <div class="result-con">
          <div class="time" data-datetime="2026-04-21T18:00:00+00:00"></div>
          <div class="team team1">Spirit</div>
          <div class="result-score"><span>2</span><span>1</span></div>
          <div class="team team2">FaZe</div>
          <div class="map-text">bo3</div>
          <div class="event-name">BLAST Open Lisbon 2026</div>
        </div>
      </a>
    </div>
    """
    primary_client = FakeMatchesBrowserClient(
        {
            "/results": single_results_html,
            detail_url: "<html><body>broken</body></html>",
        },
        headless=True,
    )
    headful_client = FakeMatchesBrowserClient(
        {detail_url: _read_fixture("hltv_match_detail.html")},
        headless=False,
    )

    class FakeHLTVBrowserClient:
        @staticmethod
        def from_config(config: HLTVConfig) -> FakeMatchesBrowserClient:
            return primary_client

        def __new__(
            cls,
            *,
            base_url: str,
            headless: bool,
            request_timeout_seconds: int,
            min_request_interval_seconds: float,
            playwright_factory: object | None = None,
            sleep: object | None = None,
            monotonic: object | None = None,
        ) -> FakeMatchesBrowserClient:
            return headful_client if not headless else primary_client

    monkeypatch.setattr(hltv_matches_module, "HLTVBrowserClient", FakeHLTVBrowserClient, raising=False)
    monkeypatch.setattr(
        hltv_matches_module.HLTVMatchesCollector,
        "_fetch_top_ranked_team_names_from_rankings",
        no_rankings,
        raising=False,
    )

    collector = hltv_matches_module.HLTVMatchesCollector(
        now=lambda: datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )

    items = await collector.collect()

    assert primary_client.calls == ["/results", detail_url, detail_url]
    assert primary_client.wait_until_calls == ["domcontentloaded", "domcontentloaded", "load"]
    assert headful_client.calls == [detail_url]
    assert headful_client.wait_until_calls == ["load"]
    assert headful_client.closed is True
    assert [item.metadata["external_id"] for item in items] == ["2412345"]


def test_main_registers_hltv_matches_collector() -> None:
    from overpass.collectors.hltv_matches import HLTVMatchesCollector
    from overpass.main import COLLECTORS

    assert any(isinstance(collector, HLTVMatchesCollector) for collector in COLLECTORS)


def test_digest_exposes_matches_section_name_for_match_items() -> None:
    from overpass.editorial.digest import SECTION_NAMES

    assert SECTION_NAMES["match"] == "Matches"
