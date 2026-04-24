"""Tests for overpass.history.lookup."""

from __future__ import annotations

from datetime import date

import pytest

from overpass.history import lookup as lookup_module
from overpass.history.lookup import get_primary_for
from overpass.history.models import HistoryDay, HistoryEntry


@pytest.fixture
def patched_history(monkeypatch):
    primary = HistoryEntry(year=2018, headline="C9 win Boston", narrative="Triple OT.")
    alt = HistoryEntry(year=2017, headline="alt", narrative="alt")
    fake = {"03-04": HistoryDay(primary=primary, alternatives=[alt])}
    monkeypatch.setattr(lookup_module, "load_history", lambda: fake)
    return primary


def test_returns_primary_for_known_date(patched_history):
    result = get_primary_for(date(2026, 3, 4))
    assert result is patched_history


def test_returns_none_for_missing_date(patched_history):
    assert get_primary_for(date(2026, 1, 1)) is None


def test_lookup_is_year_agnostic(patched_history):
    # Any year, same MM-DD, returns the same primary.
    assert get_primary_for(date(2030, 3, 4)) is patched_history
    assert get_primary_for(date(1999, 3, 4)) is patched_history


def test_pads_single_digit_month_and_day(monkeypatch):
    primary = HistoryEntry(year=2014, headline="x", narrative="y")
    fake = {"01-05": HistoryDay(primary=primary)}
    monkeypatch.setattr(lookup_module, "load_history", lambda: fake)
    assert get_primary_for(date(2026, 1, 5)) is primary
