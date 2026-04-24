"""Unit tests for overpass.history.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from overpass.history.models import HistoryDay, HistoryEntry


def test_history_entry_minimum_required_fields():
    entry = HistoryEntry(year=2018, headline="C9 win Boston", narrative="They did.")
    assert entry.year == 2018
    assert entry.visual_label is None
    assert entry.source_url is None


def test_history_entry_rejects_year_before_1999():
    with pytest.raises(ValidationError):
        HistoryEntry(year=1998, headline="x", narrative="y")


def test_history_entry_rejects_empty_headline():
    with pytest.raises(ValidationError):
        HistoryEntry(year=2018, headline="", narrative="y")


def test_history_entry_rejects_empty_narrative():
    with pytest.raises(ValidationError):
        HistoryEntry(year=2018, headline="x", narrative="")


def test_history_day_defaults_alternatives_to_empty_list():
    day = HistoryDay(primary=HistoryEntry(year=2018, headline="x", narrative="y"))
    assert day.alternatives == []


def test_history_day_accepts_alternatives():
    primary = HistoryEntry(year=2018, headline="a", narrative="b")
    alt = HistoryEntry(year=2017, headline="c", narrative="d")
    day = HistoryDay(primary=primary, alternatives=[alt])
    assert day.alternatives[0].year == 2017
