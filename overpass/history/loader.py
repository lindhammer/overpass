"""Load and validate the 'This Day in CS' YAML dataset."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from overpass.history.models import HistoryDay

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "this_day_in_cs.yaml"


def _validate_key(key: str) -> str | None:
    """Return an error message if `key` is not a valid MM-DD calendar date."""
    if not isinstance(key, str) or len(key) != 5 or key[2] != "-":
        return f"key {key!r}: must be a 'MM-DD' string"
    try:
        month = int(key[:2])
        day = int(key[3:])
    except ValueError:
        return f"key {key!r}: month/day must be integers"
    try:
        # Year 2000 is a leap year, so 02-29 is accepted; 02-30 is not.
        date(2000, month, day)
    except ValueError as exc:
        return f"key {key!r}: {exc}"
    return None


def _load_from_path(path: Path) -> dict[str, HistoryDay]:
    """Load and eagerly validate a history YAML file. Lists every bad bucket."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping, got {type(raw).__name__}")

    errors: list[str] = []
    parsed: dict[str, HistoryDay] = {}

    for key, value in raw.items():
        key_str = str(key)
        key_err = _validate_key(key_str)
        if key_err is not None:
            errors.append(key_err)
            continue
        try:
            parsed[key_str] = HistoryDay.model_validate(value)
        except ValidationError as exc:
            errors.append(f"key {key_str!r}: {exc}")

    if errors:
        joined = "\n  - ".join(errors)
        raise ValueError(f"{path}: invalid entries:\n  - {joined}")

    return parsed


@lru_cache(maxsize=1)
def load_history() -> dict[str, HistoryDay]:
    """Return the cached, validated history dataset."""
    return _load_from_path(_DATA_PATH)
