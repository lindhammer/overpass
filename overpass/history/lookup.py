"""Resolve today's primary 'This Day in CS' entry."""

from __future__ import annotations

from datetime import date

from overpass.history.loader import load_history
from overpass.history.models import HistoryEntry


def get_primary_for(today: date) -> HistoryEntry | None:
    """Return the primary entry for `today`'s MM-DD bucket, or None if absent."""
    key = today.strftime("%m-%d")
    day = load_history().get(key)
    return day.primary if day is not None else None
