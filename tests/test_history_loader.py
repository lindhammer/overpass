"""Tests for overpass.history.loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from overpass.history.loader import load_history, _load_from_path
from overpass.history.models import HistoryDay


def test_real_seed_yaml_loads_and_validates():
    """The shipped seed dataset must always parse cleanly."""
    data = load_history()
    assert len(data) >= 1
    for key, day in data.items():
        assert isinstance(day, HistoryDay)
        # Key must be a real calendar date (e.g. "02-30" would be rejected).
        date(2000, int(key[:2]), int(key[3:]))


def test_load_from_path_rejects_bad_calendar_key(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        '"02-30":\n'
        '  primary:\n'
        '    year: 2018\n'
        '    headline: x\n'
        '    narrative: y\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_from_path(bad)
    assert "02-30" in str(exc.value)


def test_load_from_path_rejects_malformed_key(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        '"2018-03-04":\n'
        '  primary:\n'
        '    year: 2018\n'
        '    headline: x\n'
        '    narrative: y\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_from_path(bad)
    assert "2018-03-04" in str(exc.value)


def test_load_from_path_lists_every_bad_bucket(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        '"02-30":\n'
        '  primary:\n'
        '    year: 2018\n'
        '    headline: x\n'
        '    narrative: y\n'
        '"13-01":\n'
        '  primary:\n'
        '    year: 2018\n'
        '    headline: x\n'
        '    narrative: y\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_from_path(bad)
    msg = str(exc.value)
    assert "02-30" in msg
    assert "13-01" in msg


def test_load_from_path_rejects_invalid_entry(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        '"03-04":\n'
        '  primary:\n'
        '    year: 1990\n'
        '    headline: x\n'
        '    narrative: y\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_from_path(bad)
    assert "03-04" in str(exc.value)


def test_load_history_is_cached():
    first = load_history()
    second = load_history()
    assert first is second
