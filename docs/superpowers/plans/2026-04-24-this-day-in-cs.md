# This Day in CS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a curated, date-keyed historical CS moment in each daily briefing, sourced from a repo-tracked YAML file.

**Architecture:** A new `overpass/history/` package owns Pydantic models, a cached YAML loader, and a date lookup. `delivery/html.py` flattens the chosen entry into the dict shape the template already expects; `main.py` wires the lookup into the pipeline. No network, no LLM, no DB.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, Jinja2 (already wired), pytest. Project venv: `.venv` (Windows; activate with `.venv\Scripts\Activate.ps1`).

**Spec:** `docs/superpowers/specs/2026-04-24-this-day-in-cs-design.md`

---

## File map

- Create: `overpass/history/__init__.py` — re-exports `HistoryEntry`, `HistoryDay`, `load_history`, `get_primary_for`.
- Create: `overpass/history/models.py` — `HistoryEntry`, `HistoryDay`.
- Create: `overpass/history/loader.py` — `load_history()` cached, eager validation.
- Create: `overpass/history/lookup.py` — `get_primary_for(today)`.
- Create: `overpass/data/this_day_in_cs.yaml` — seed dataset (~15 entries).
- Modify: `overpass/delivery/html.py` — add `_history_entry_to_dict`, extend `render_briefing` signature + context.
- Modify: `overpass/main.py` — call `get_primary_for(today)` and pass to `render_briefing`.
- Create: `tests/test_history_models.py` — unit tests for the Pydantic models.
- Create: `tests/test_history_loader.py` — schema regression test against the real seed YAML.
- Create: `tests/test_history_lookup.py` — `get_primary_for` behavior with patched loader.
- Modify: `tests/test_html_delivery.py` — two new test cases (rendered + omitted).

---

## Task 1: History models

**Files:**

- Create: `overpass/history/__init__.py`
- Create: `overpass/history/models.py`
- Create: `tests/test_history_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'overpass.history'`.

- [ ] **Step 3: Create the package marker**

Create `overpass/history/__init__.py`:

```python
"""History feature: 'This Day in CS' curated lookups."""

from overpass.history.models import HistoryDay, HistoryEntry

__all__ = ["HistoryDay", "HistoryEntry"]
```

- [ ] **Step 4: Implement the models**

Create `overpass/history/models.py`:

```python
"""Pydantic models for the 'This Day in CS' dataset."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryEntry(BaseModel):
    """A single curated historical moment."""

    year: int = Field(ge=1999)
    headline: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    visual_label: str | None = None
    source_url: str | None = None


class HistoryDay(BaseModel):
    """All entries bucketed under a single MM-DD key."""

    primary: HistoryEntry
    alternatives: list[HistoryEntry] = []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_models.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add overpass/history/__init__.py overpass/history/models.py tests/test_history_models.py
git commit -m "feat(history): add HistoryEntry and HistoryDay models"
```

---

## Task 2: Seed YAML dataset

**Files:**

- Create: `overpass/data/this_day_in_cs.yaml`

- [ ] **Step 1: Create the seed file**

Create `overpass/data/this_day_in_cs.yaml`:

```yaml
# Curated "This Day in CS" entries, keyed by zero-padded MM-DD.
# Each bucket has one `primary` entry rendered in the briefing; `alternatives`
# is a free-form list reserved for future rotation logic.
# Year must be >= 1999. Headline + narrative are required. visual_label is
# the short watermark (falls back to the year). source_url is optional.

"01-31":
  primary:
    year: 2016
    headline: "Astralis is founded as a player-owned org"
    narrative: |
      The TSM CS:GO roster (dev1ce, dupreeh, Xyp9x, Kjaerbye, karrigan)
      formally launches Astralis as a player-owned organisation, setting
      up what would become the most decorated lineup in the game's history.
    visual_label: "AST '16"
    source_url: "https://liquipedia.net/counterstrike/Astralis"
  alternatives: []

"03-16":
  primary:
    year: 2014
    headline: "Virtus.pro win EMS One Katowice"
    narrative: |
      Virtus.pro lift the trophy at the first CS:GO Major, EMS One Katowice,
      kicking off the Polish dynasty era and the modern Major circuit.
    visual_label: "KAT '14"
    source_url: "https://liquipedia.net/counterstrike/EMS/One/Katowice/2014"
  alternatives: []

"03-04":
  primary:
    year: 2018
    headline: "Cloud9 win the ELEAGUE Boston Major"
    narrative: |
      Cloud9 become the first North American team to win a CS:GO Major,
      beating FaZe 2-1 in Boston after a triple-overtime Inferno decider.
    visual_label: "BOS '18"
    source_url: "https://liquipedia.net/counterstrike/ELEAGUE/Major/2018"
  alternatives: []

"04-04":
  primary:
    year: 2014
    headline: "Operation Bravo introduces the workshop pipeline"
    narrative: |
      Valve ships Operation Bravo, the first sustained run of community-built
      maps in CS:GO matchmaking and the template every later Operation
      followed.
    visual_label: "OP BRV"
    source_url: "https://liquipedia.net/counterstrike/Operation_Bravo"
  alternatives: []

"04-07":
  primary:
    year: 2024
    headline: "NaVi win PGL Major Copenhagen"
    narrative: |
      Natus Vincere take the first CS2 Major, beating FaZe 2-0 in the
      Copenhagen final and confirming the new engine had a competitive
      apex worth chasing.
    visual_label: "CPH '24"
    source_url: "https://liquipedia.net/counterstrike/PGL/Major/2024/Copenhagen"
  alternatives: []

"05-21":
  primary:
    year: 2023
    headline: "Vitality win the BLAST.tv Paris Major"
    narrative: |
      Vitality beat GamerLegion 2-0 in Paris, closing out the final CS:GO
      Major and giving ZywOo his first Major trophy on home soil.
    visual_label: "PAR '23"
    source_url: "https://liquipedia.net/counterstrike/BLAST/Major/2023/Paris"
  alternatives: []

"06-08":
  primary:
    year: 2017
    headline: "Gambit win the PGL Krakow Major"
    narrative: |
      Gambit upset Immortals 2-1 in the Krakow final, the last European
      Major before the North American Boston run and the high-water mark
      of the CIS scene's first wave.
    visual_label: "KRK '17"
    source_url: "https://liquipedia.net/counterstrike/PGL/Major/2017/Krakow"
  alternatives: []

"07-05":
  primary:
    year: 2015
    headline: "Fnatic win ESL One Cologne"
    narrative: |
      Fnatic beat EnVyUs 2-1 in the Cologne final, a series remembered
      both for the championship and for the controversial Olofmeister
      boost on Overpass.
    visual_label: "CGN '15"
    source_url: "https://liquipedia.net/counterstrike/ESL/One/Cologne/2015"
  alternatives: []

"07-22":
  primary:
    year: 2018
    headline: "Astralis complete the Intel Grand Slam"
    narrative: |
      Astralis win FACEIT London, sealing the first ever Intel Grand Slam
      and cementing their 2018-19 dynasty as the strongest in CS history.
    visual_label: "GS '18"
    source_url: "https://liquipedia.net/counterstrike/FACEIT/Major/2018/London"
  alternatives: []

"08-12":
  primary:
    year: 2012
    headline: "Counter-Strike: Global Offensive ships"
    narrative: |
      Valve releases CS:GO on Windows, OS X, Xbox 360, and PS3, replacing
      Source as the competitive entry and starting the decade-plus run
      this dataset chronicles.
    visual_label: "CS:GO"
    source_url: "https://liquipedia.net/counterstrike/Counter-Strike:_Global_Offensive"
  alternatives: []

"09-27":
  primary:
    year: 2023
    headline: "Counter-Strike 2 launches"
    narrative: |
      CS2 ships as a free upgrade to CS:GO, replacing it overnight on
      Steam and bringing the Source 2 engine, sub-tick networking, and
      the volumetric smoke rework to competitive play.
    visual_label: "CS2"
    source_url: "https://liquipedia.net/counterstrike/Counter-Strike_2"
  alternatives: []

"10-30":
  primary:
    year: 2016
    headline: "Astralis win their first Major in Atlanta"
    narrative: |
      Astralis beat Virtus.pro 2-1 at ELEAGUE Atlanta to claim their
      first Major trophy, a result that reframed the Danish project
      from contender to era-defining.
    visual_label: "ATL '17"
    source_url: "https://liquipedia.net/counterstrike/ELEAGUE/Major/2017"
  alternatives: []

"11-07":
  primary:
    year: 2021
    headline: "NaVi win the PGL Stockholm Major"
    narrative: |
      Natus Vincere drop a single map across the entire bracket and beat
      G2 in the Stockholm final, giving s1mple his long-awaited first
      Major trophy.
    visual_label: "STO '21"
    source_url: "https://liquipedia.net/counterstrike/PGL/Major/2021/Stockholm"
  alternatives: []

"11-19":
  primary:
    year: 2017
    headline: "SK Gaming close out a record-setting year"
    narrative: |
      The Brazilian SK Gaming roster (FalleN, coldzera, fer, TACO, boltz)
      cap off a 2017 in which coldzera won HLTV Player of the Year for
      the second straight season.
    visual_label: "SK '17"
    source_url: "https://liquipedia.net/counterstrike/SK_Gaming"
  alternatives: []

"12-09":
  primary:
    year: 2018
    headline: "coldzera takes a third top-20 podium"
    narrative: |
      HLTV's end-of-year ranking confirms coldzera in the top three for
      the third year running, the first player to ever do so and a
      benchmark s1mple would later chase down.
    visual_label: "HLTV '18"
    source_url: "https://www.hltv.org/news/26602/top-20-players-of-2018-coldzera-3"
  alternatives: []
```

- [ ] **Step 2: Sanity-check it parses**

Run:

```powershell
.venv\Scripts\python.exe -c "import yaml, pathlib; data = yaml.safe_load(pathlib.Path('overpass/data/this_day_in_cs.yaml').read_text(encoding='utf-8')); print(len(data), 'buckets'); print(sorted(data.keys()))"
```

Expected: prints `15 buckets` followed by the sorted MM-DD list.

- [ ] **Step 3: Commit**

```bash
git add overpass/data/this_day_in_cs.yaml
git commit -m "feat(history): seed 'This Day in CS' dataset (15 entries)"
```

---

## Task 3: YAML loader with eager validation

**Files:**

- Create: `overpass/history/loader.py`
- Modify: `overpass/history/__init__.py`
- Create: `tests/test_history_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_loader.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_loader.py -v`
Expected: FAIL with `ImportError: cannot import name '_load_from_path' from 'overpass.history.loader'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Implement the loader**

Create `overpass/history/loader.py`:

```python
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
```

- [ ] **Step 4: Update package exports**

Replace `overpass/history/__init__.py` with:

```python
"""History feature: 'This Day in CS' curated lookups."""

from overpass.history.loader import load_history
from overpass.history.models import HistoryDay, HistoryEntry

__all__ = ["HistoryDay", "HistoryEntry", "load_history"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_loader.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add overpass/history/loader.py overpass/history/__init__.py tests/test_history_loader.py
git commit -m "feat(history): add YAML loader with eager validation"
```

---

## Task 4: Date lookup

**Files:**

- Create: `overpass/history/lookup.py`
- Modify: `overpass/history/__init__.py`
- Create: `tests/test_history_lookup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_lookup.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_lookup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'overpass.history.lookup'`.

- [ ] **Step 3: Implement the lookup**

Create `overpass/history/lookup.py`:

```python
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
```

- [ ] **Step 4: Update package exports**

Replace `overpass/history/__init__.py` with:

```python
"""History feature: 'This Day in CS' curated lookups."""

from overpass.history.loader import load_history
from overpass.history.lookup import get_primary_for
from overpass.history.models import HistoryDay, HistoryEntry

__all__ = ["HistoryDay", "HistoryEntry", "get_primary_for", "load_history"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_history_lookup.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add overpass/history/lookup.py overpass/history/__init__.py tests/test_history_lookup.py
git commit -m "feat(history): add get_primary_for date lookup"
```

---

## Task 5: Render integration in `delivery/html.py`

**Files:**

- Modify: `overpass/delivery/html.py`
- Modify: `tests/test_html_delivery.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_html_delivery.py` (after the existing imports + helpers; the file already imports `render_briefing`, `_DATE`, etc.):

```python
# ── This Day in CS ───────────────────────────────────────────────

from overpass.history.models import HistoryEntry


def _digest_with_one_section() -> DigestOutput:
    """Minimal digest the renderer accepts (reuses existing fixtures upstream)."""
    return DigestOutput(
        summary_line="Test summary.",
        sections={"Reddit Clips": SectionOutput(intro="", items=[_clip()])},
    )


def test_render_briefing_includes_this_day_section_when_entry_passed():
    digest = _digest_with_one_section()
    entry = HistoryEntry(
        year=2018,
        headline="Cloud9 win the ELEAGUE Boston Major",
        narrative="C9 beat FaZe 2-1 in Boston after triple OT on Inferno.",
        visual_label="BOS '18",
        source_url="https://liquipedia.net/counterstrike/ELEAGUE/Major/2018",
    )
    html = render_briefing(digest, _DATE, this_day=entry)
    assert "This Day in CS" in html
    assert "Cloud9 win the ELEAGUE Boston Major" in html
    assert "C9 beat FaZe 2-1 in Boston" in html
    assert "BOS &#39;18" in html or "BOS '18" in html
    # date_label is computed from the entry year + briefing month/day:
    assert "April 10, 2018" in html
    assert "https://liquipedia.net/counterstrike/ELEAGUE/Major/2018" in html


def test_render_briefing_omits_this_day_section_when_none():
    digest = _digest_with_one_section()
    html = render_briefing(digest, _DATE)
    assert "This Day in CS" not in html


def test_render_briefing_falls_back_to_year_when_no_visual_label():
    digest = _digest_with_one_section()
    entry = HistoryEntry(
        year=2018,
        headline="x",
        narrative="y",
    )
    html = render_briefing(digest, _DATE, this_day=entry)
    # The template renders `visual_label or year`; with no label, "2018" appears.
    assert "2018" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_delivery.py -v`
Expected: the three new tests FAIL with `TypeError: render_briefing() got an unexpected keyword argument 'this_day'`.

- [ ] **Step 3: Add the flatten helper and extend `render_briefing`**

In `overpass/delivery/html.py`, add this import near the existing model imports at the top:

```python
from overpass.history.models import HistoryEntry
```

Add this helper just below `_upcoming_match_to_dict` (around line 200):

```python
def _history_entry_to_dict(entry: HistoryEntry, briefing_date: date) -> dict[str, Any]:
    """Flatten a HistoryEntry into the dict shape the template expects."""
    label_date = date(entry.year, briefing_date.month, briefing_date.day)
    return {
        "year": entry.year,
        "date_label": _fmt_date(label_date, "%B %-d, %Y"),
        "headline": entry.headline,
        "narrative": entry.narrative,
        "visual_label": entry.visual_label,
        "source_url": entry.source_url,
    }
```

Replace the existing `render_briefing` signature and body with:

```python
def render_briefing(
    digest: DigestOutput,
    briefing_date: date,
    *,
    social_items: list[CollectorItem] | None = None,
    upcoming_items: list[CollectorItem] | None = None,
    this_day: HistoryEntry | None = None,
) -> str:
    """Render the briefing template and return the HTML string."""
    env = _make_env()
    template = env.get_template("briefing.html")
    social_posts = [_social_post_to_dict(it) for it in (social_items or [])]
    upcoming_matches = [_upcoming_match_to_dict(it) for it in (upcoming_items or [])]
    this_day_ctx = (
        _history_entry_to_dict(this_day, briefing_date) if this_day is not None else None
    )
    context: dict[str, Any] = {
        "digest": digest,
        "date": briefing_date,
        "generated_at": datetime.now(),
        "issue_no": _compute_issue_number(briefing_date),
        "ticker_chips": _build_ticker_chips(digest),
        "sources": _collect_sources(digest),
        "social_posts": social_posts,
        "upcoming_matches": upcoming_matches,
        "this_day": this_day_ctx,
        "per_match_blurbs": {
            url: blurb.model_dump() for url, blurb in digest.per_match_blurbs.items()
        },
    }
    return template.render(**context)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_delivery.py -v`
Expected: all tests pass, including the three new ones.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: no regressions (the one known-flaky `test_liquipedia_ratelimit::test_concurrent_calls_are_serialised` may fail; re-run that file alone to confirm it's the timing issue, not new breakage).

- [ ] **Step 6: Commit**

```bash
git add overpass/delivery/html.py tests/test_html_delivery.py
git commit -m "feat(delivery): render 'This Day in CS' section when entry provided"
```

---

## Task 6: Wire into the pipeline

**Files:**

- Modify: `overpass/main.py`

- [ ] **Step 1: Add the import**

In `overpass/main.py`, add to the imports block (alphabetical placement next to `overpass.editorial.*`):

```python
from overpass.history.lookup import get_primary_for
```

- [ ] **Step 2: Compute and pass `this_day` in the render step**

Locate this block in `async_main`:

```python
    # ── 3. HTML briefing ─────────────────────────────────────────
    logger.info("=== Step 3/4: Rendering HTML ===")
    t0 = time.monotonic()
    today = date.today()
    html = render_briefing(
        digest,
        today,
        social_items=social_items,
        upcoming_items=upcoming_items,
    )
```

Replace it with:

```python
    # ── 3. HTML briefing ─────────────────────────────────────────
    logger.info("=== Step 3/4: Rendering HTML ===")
    t0 = time.monotonic()
    today = date.today()
    this_day = get_primary_for(today)
    if this_day is not None:
        logger.info("This Day in CS: %d — %s", this_day.year, this_day.headline)
    else:
        logger.info("This Day in CS: no entry for %s", today.isoformat())
    html = render_briefing(
        digest,
        today,
        social_items=social_items,
        upcoming_items=upcoming_items,
        this_day=this_day,
    )
```

- [ ] **Step 3: Smoke-check the import wiring**

Run:

```powershell
.venv\Scripts\python.exe -c "from overpass.main import async_main; from overpass.history.lookup import get_primary_for; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: same green baseline as before (modulo the known flaky ratelimit timing test).

- [ ] **Step 5: Commit**

```bash
git add overpass/main.py
git commit -m "feat(main): wire 'This Day in CS' lookup into pipeline"
```

---

## Self-review checklist (run after Task 6)

- [ ] Spec section "Data file" → covered by Task 2.
- [ ] Spec section "Code layout" (`models.py`/`loader.py`/`lookup.py`) → covered by Tasks 1, 3, 4.
- [ ] Spec section "Render integration" (`_history_entry_to_dict`, `render_briefing` kwarg, `main.py`) → covered by Tasks 5, 6.
- [ ] Spec section "Testing" (loader / lookup / html delivery) → covered by Tasks 1, 3, 4, 5.
- [ ] No new config keys, env vars, or CLI flags introduced (per spec).
- [ ] `date_label` is computed at render time, not stored in YAML (per spec).

