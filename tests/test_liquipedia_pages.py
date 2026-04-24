"""Page-finder tests — token filter, soft-fail on no matches."""

from __future__ import annotations

import asyncio

import pytest

from overpass.liquipedia.pages import find_match_page


class _StubClient:
    def __init__(self, titles: list[str]) -> None:
        self._titles = titles
        self.queries: list[str] = []

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        self.queries.append(query)
        return self._titles


class _QueryStubClient:
    def __init__(self, titles_by_query: dict[str, list[str]]) -> None:
        self._titles_by_query = titles_by_query
        self.queries: list[str] = []

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        self.queries.append(query)
        return self._titles_by_query.get(query, [])


def test_find_match_page_returns_first_token_matching_title() -> None:
    client = _StubClient(
        titles=[
            "Some Other Tournament",
            "BetBoom RUSH B Summit/Season 3",
            "BetBoom RUSH B Summit/Season 2",
        ]
    )
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result == "BetBoom RUSH B Summit/Season 3"


def test_find_match_page_returns_none_when_no_titles_match_token() -> None:
    client = _StubClient(titles=["Unrelated Page", "Another Thing"])
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result is None


def test_find_match_page_returns_none_on_empty_results() -> None:
    client = _StubClient(titles=[])
    result = asyncio.run(find_match_page(client, "Anything"))
    assert result is None


def test_find_match_page_returns_none_for_empty_event_name() -> None:
    client = _StubClient(titles=["Whatever"])
    result = asyncio.run(find_match_page(client, ""))
    assert result is None
    assert client.queries == []  # no API call made


def test_find_match_page_token_match_is_case_insensitive() -> None:
    client = _StubClient(titles=["betboom rush b summit/season 3"])
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result == "betboom rush b summit/season 3"


def test_find_match_page_tries_event_name_without_sponsor_prefix() -> None:
    client = _QueryStubClient(
        {
            "Tipsport Conquest of Prague 2026": [],
            "Conquest of Prague 2026": [
                "PLAYzone/Conquest of Prague/2026/Online Stage",
            ],
        }
    )

    result = asyncio.run(find_match_page(client, "Tipsport Conquest of Prague 2026"))

    assert result == "PLAYzone/Conquest of Prague/2026/Online Stage"
    assert client.queries == [
        "Tipsport Conquest of Prague 2026",
        "Conquest of Prague 2026",
    ]


def test_find_match_page_ranks_season_number_named_as_part_word() -> None:
    client = _StubClient(
        titles=[
            "BetBoom/RUSH B! Summit/2026",
            "BetBoom/RUSH B! Summit/2026/Part Deux",
            "BetBoom/RUSH B! Summit/2026/Part Three",
        ]
    )

    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))

    assert result == "BetBoom/RUSH B! Summit/2026/Part Three"


def test_find_match_page_allows_liquipedia_series_word_insertions() -> None:
    client = _StubClient(titles=["CCT/Season 3/Global Finals"])

    result = asyncio.run(find_match_page(client, "CCT Global Finals 2026"))

    assert result == "CCT/Season 3/Global Finals"


def test_find_match_page_rejects_weak_stale_sponsor_match() -> None:
    client = _StubClient(titles=["Tipsport Cup/2022/Prague"])

    result = asyncio.run(find_match_page(client, "Tipsport Conquest of Prague 2026"))

    assert result is None
