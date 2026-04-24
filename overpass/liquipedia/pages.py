"""Page-finder — map an HLTV event_name to a Liquipedia page title."""

from __future__ import annotations

import re
from typing import Protocol


class _SupportsSearch(Protocol):
    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]: ...


_NUMBER_WORDS = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"of", "the", "and"}


async def find_match_page(
    client: _SupportsSearch, event_name: str
) -> str | None:
    """Find the best Liquipedia page title for an HLTV event name.

    Args:
        client: Object that can search Liquipedia page titles.
        event_name: HLTV event name used to generate conservative search
            variants and token-overlap scoring.

    Returns:
        Best-matching Liquipedia page title, or None for empty input or no
        plausible match.
    """
    if not event_name or not event_name.strip():
        return None

    event_name = event_name.strip()
    wanted_tokens = _tokens_for_match(event_name)

    for query in _query_variants(event_name):
        titles = await client.search_page_titles(query, limit=5)
        title = _best_title(titles, wanted_tokens)
        if title is not None:
            return title
    return None


def _query_variants(event_name: str) -> list[str]:
    variants = [event_name]
    parts = event_name.split()
    if len(parts) > 3:
        variants.append(" ".join(parts[1:]))

    for value in list(variants):
        without_season = re.sub(r"\s+Season\s+\d+\b", "", value, flags=re.IGNORECASE).strip()
        if without_season != value:
            variants.append(without_season)

        without_year = re.sub(r"\s+\d{4}\b", "", value).strip()
        if without_year != value:
            variants.append(without_year)

    if parts:
        variants.append(parts[0])

    unique_variants: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        normalized = variant.casefold()
        if variant and normalized not in seen:
            seen.add(normalized)
            unique_variants.append(variant)
    return unique_variants


def _best_title(titles: list[str], wanted_tokens: set[str]) -> str | None:
    if not titles or not wanted_tokens:
        return None

    minimum_score = min(3, len(wanted_tokens))
    best_title: str | None = None
    best_score = 0
    for title in titles:
        score = len(wanted_tokens & _tokens_for_match(title))
        if score > best_score:
            best_title = title
            best_score = score

    if best_score < minimum_score:
        return None
    return best_title


def _tokens_for_match(value: str) -> set[str]:
    lowered = value.casefold()
    tokens = {
        token
        for token in _TOKEN_PATTERN.findall(lowered)
        if token not in _STOPWORDS and (len(token) >= 3 or token.isdigit())
    }

    for match in re.finditer(r"\b(?:season|part)\s+(\d{1,2})\b", lowered):
        word = _NUMBER_WORDS.get(match.group(1))
        if word is not None:
            tokens.add(word)

    return tokens
