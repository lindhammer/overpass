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
