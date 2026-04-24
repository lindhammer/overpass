"""HLTVMatchesCollector falls back to Liquipedia when match-detail parsing fails."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from overpass.collectors.hltv_matches import (
    HLTVMatchesCollector,
    _liquipedia_page_title_candidates,
)
from overpass.hltv.models import HLTVMatchResult
from overpass.liquipedia.models import LiquipediaMap, LiquipediaMatch


def _listing_item() -> HLTVMatchResult:
    return HLTVMatchResult(
        external_id="123",
        url="https://www.hltv.org/matches/123/x-vs-y",
        team1_name="Legacy",
        team2_name="ALZON",
        team1_score=0,  # bogus listing scores; detail parse should overwrite
        team2_score=0,
        event_name="BetBoom RUSH B Summit Season 3",
        format="bo3",
        played_at=datetime(2026, 4, 23, 4, 25, tzinfo=timezone.utc),
    )


class _StubLiquipediaClient:
    def __init__(self, match: LiquipediaMatch | None) -> None:
        self._match = match

    async def parse_page(self, page_title: str) -> str:
        return "<html><body>stub</body></html>"

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        return ["BetBoom RUSH B Summit/Season 3"]

    async def close(self) -> None:
        pass


def _stub_browser_client():
    client = AsyncMock()
    client.fetch_page_content = AsyncMock(return_value="<html>broken</html>")
    client.base_url = "https://www.hltv.org"
    client.headless = True
    client.close = AsyncMock()
    return client


def test_collector_uses_liquipedia_when_hltv_detail_parse_fails() -> None:
    listing = _listing_item()
    fallback_match = LiquipediaMatch(
        team1_name="Legacy",
        team2_name="ALZON",
        team1_score=2,
        team2_score=0,
        winner_name="Legacy",
        maps=[
            LiquipediaMap(name="Nuke", team1_score=13, team2_score=1),
            LiquipediaMap(name="Mirage", team1_score=13, team2_score=3),
        ],
    )
    liq_client = _StubLiquipediaClient(fallback_match)

    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=liq_client,
    )

    with patch(
        "overpass.collectors.hltv_matches.parse_match_from_tournament_page",
        return_value=fallback_match,
    ), patch(
        "overpass.collectors.hltv_matches.find_match_page",
        new=AsyncMock(return_value="BetBoom RUSH B Summit/Season 3"),
    ):
        detail = asyncio.run(collector._collect_match_detail(listing))

    assert detail.team1_score == 2
    assert detail.team2_score == 0
    assert [m.name for m in detail.maps] == ["Nuke", "Mirage"]
    item = collector._to_collector_item(detail)
    assert item.metadata["source_fallback"] == "liquipedia"


def test_collector_drops_match_when_liquipedia_also_fails() -> None:
    listing = _listing_item()
    liq_client = _StubLiquipediaClient(None)

    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=liq_client,
    )

    with patch(
        "overpass.collectors.hltv_matches.find_match_page",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(Exception):
            asyncio.run(collector._collect_match_detail(listing))


def test_collector_without_liquipedia_client_raises_as_today() -> None:
    listing = _listing_item()
    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=None,
    )
    with pytest.raises(Exception):
        asyncio.run(collector._collect_match_detail(listing))


def test_liquipedia_page_title_candidates_include_betboom_part_from_season() -> None:
    listing = _listing_item()

    candidates = _liquipedia_page_title_candidates(
        listing,
        found_title="BetBoom/RUSH B! Summit/2026/Part Deux",
    )

    assert candidates[:2] == [
        "BetBoom/RUSH B! Summit/2026/Part Deux",
        "BetBoom/RUSH B! Summit/2026/Part Three",
    ]


def test_liquipedia_page_title_candidates_include_online_stage_sibling() -> None:
    listing = _listing_item()
    listing.event_name = "Tipsport Conquest of Prague 2026"

    candidates = _liquipedia_page_title_candidates(
        listing,
        found_title="PLAYzone/Conquest of Prague/2026",
    )

    assert "PLAYzone/Conquest of Prague/2026/Online Stage" in candidates
