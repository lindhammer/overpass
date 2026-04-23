"""Page-finder — map an HLTV event_name to a Liquipedia page title."""

from __future__ import annotations

from typing import Protocol


class _SupportsSearch(Protocol):
    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]: ...


_MIN_TOKEN_LEN = 4


async def find_match_page(
    client: _SupportsSearch, event_name: str
) -> str | None:
    """Return the best-matching Liquipedia page title for *event_name*.

    Strategy: opensearch the event name, then keep only candidates whose
    title (case-insensitive) contains the longest token from the event
    name of length >= _MIN_TOKEN_LEN. Return the first survivor, or None
    on no survivors / empty input. We bias towards None on ambiguity to
    avoid injecting wrong data downstream.
    """
    if not event_name or not event_name.strip():
        return None

    tokens = [t for t in event_name.split() if len(t) >= _MIN_TOKEN_LEN]
    if not tokens:
        # Fall back to the whole event name as a single token.
        tokens = [event_name.strip()]
    longest = max(tokens, key=len).lower()

    titles = await client.search_page_titles(event_name, limit=5)
    for title in titles:
        if longest in title.lower():
            return title
    return None
