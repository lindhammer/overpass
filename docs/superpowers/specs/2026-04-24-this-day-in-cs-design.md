# This Day in CS — Design

**Date:** 2026-04-24
**Phase:** 4 (per `SPEC.md`)
**Status:** Draft for review

## Goal

Surface one curated, well-written historical Counter-Strike moment in each
daily briefing, keyed by today's calendar date. Render-time behavior is
deterministic and offline; all editorial work happens in a repo-tracked YAML
file ahead of time.

The HTML template (`overpass/templates/briefing.html`) is already wired for a
`this_day` context variable with the field shape
`{year, date_label, headline, narrative, visual_label?, source_url?}` and
gates the entire section on `{% if this_day %}`.

## Design decisions

| # | Decision |
|---|----------|
| 1 | **Source:** curated YAML in the repo. No scraping, no runtime LLM calls. |
| 2 | **Bucketing:** multiple entries per `MM-DD` allowed; one is `primary`, the rest are `alternatives`. |
| 3 | **Copy:** fully written in the dataset (final `headline` + `narrative`); rendered verbatim. |
| 4 | **Missing date:** omit the section entirely (template's `{% if this_day %}` already does this). |
| 5 | **Initial coverage:** mechanics + ~15 seed entries spread across the calendar. |
| 6 | **Primary marker:** explicit `primary:` key plus an `alternatives: []` list, so the data shape itself prevents "two primaries" or accidental reordering. |

## Data file

Single file at `overpass/data/this_day_in_cs.yaml`, keyed by `"MM-DD"`
strings (zero-padded so they sort naturally). Year is inside each entry.

```yaml
# overpass/data/this_day_in_cs.yaml

"03-04":
  primary:
    year: 2018
    headline: "Cloud9 win the ELEAGUE Boston Major"
    narrative: |
      Cloud9 become the first North American team to win a CS:GO Major,
      beating FaZe 2-1 in Boston after a triple-overtime Inferno decider.
    visual_label: "BOS '18"
    source_url: "https://liquipedia.net/counterstrike/ELEAGUE/2018"
  alternatives: []

"07-22":
  primary:
    year: 2018
    headline: "Astralis complete the Intel Grand Slam"
    narrative: |
      Astralis win FACEIT London, sealing the first ever Intel Grand Slam
      and cementing their 2018-19 dynasty.
    visual_label: "GS '18"
    source_url: "https://liquipedia.net/counterstrike/FACEIT/Major/2018/London"
  alternatives:
    - year: 2017
      headline: "Gambit win PGL Krakow as the underdog"
      narrative: |
        Gambit upset Immortals 2-1 in the Krakow Major final, the
        last European Major before NA's Boston run.
      visual_label: "KRK '17"
      source_url: "https://liquipedia.net/counterstrike/PGL/Major/2017/Krakow"
```

### Field contract

Every entry (primary or alternative) is the same shape:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `year` | int | yes | Calendar year of the event. |
| `headline` | str | yes | One-line title; rendered as the `<h3>`. |
| `narrative` | str | yes | 1–3 short sentences; renders as the body `<p>`. Plain text only. |
| `visual_label` | str \| None | no | Short watermark text (e.g. "BOS '18"); falls back to `year`. |
| `source_url` | str \| None | no | If set, renders as a "Read more →" link. |

`date_label` is **not** stored; it's computed at render time from the bucket
key and `year`, e.g. `"April 24, 2018"`. This keeps the dataset DRY and
prevents the date string from drifting from the actual key.

## Code layout

A small new package `overpass/history/`:

```
overpass/history/
    __init__.py
    models.py     # HistoryEntry, HistoryDay (Pydantic v2)
    loader.py     # load_history() -> dict[str, HistoryDay]; cached
    lookup.py     # get_primary_for(today: date) -> HistoryEntry | None
```

### `models.py`

```python
class HistoryEntry(BaseModel):
    year: int = Field(ge=1999)            # CS 1.0 released 2000; allow 1999 for CS Beta lore
    headline: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    visual_label: str | None = None
    source_url: str | None = None

class HistoryDay(BaseModel):
    primary: HistoryEntry
    alternatives: list[HistoryEntry] = []
```

### `loader.py`

- Reads `overpass/data/this_day_in_cs.yaml` once and caches the result via a
  module-level `functools.lru_cache(maxsize=1)`-style helper.
- Validates **all** buckets eagerly. On failure, raises `ValueError` listing
  every malformed key (date string format + Pydantic error message), so a
  bad commit fails CI immediately rather than the runtime.
- Validates that `MM-DD` keys are syntactically valid calendar dates
  (so `"02-30"` is rejected at load).

### `lookup.py`

```python
def get_primary_for(today: date) -> HistoryEntry | None:
    key = today.strftime("%m-%d")
    day = load_history().get(key)
    return day.primary if day is not None else None
```

No fallback to a different date or a non-primary entry. Missing key → `None`.

## Render integration

`overpass/delivery/html.py`:

- Add `_history_entry_to_dict(entry, today)`:

  ```python
  def _history_entry_to_dict(entry: HistoryEntry, today: date) -> dict[str, Any]:
      return {
          "year": entry.year,
          "date_label": _fmt_date(date(entry.year, today.month, today.day),
                                  "%B %-d, %Y"),
          "headline": entry.headline,
          "narrative": entry.narrative,
          "visual_label": entry.visual_label,
          "source_url": entry.source_url,
      }
  ```

  Uses the existing `_fmt_date` helper for Windows compatibility.

- Extend `render_briefing(...)` signature with a new keyword-only argument:

  ```python
  def render_briefing(
      digest: DigestOutput,
      briefing_date: date,
      *,
      social_items: list[CollectorItem] | None = None,
      upcoming_items: list[CollectorItem] | None = None,
      this_day: HistoryEntry | None = None,
  ) -> str:
  ```

  Pass `this_day=_history_entry_to_dict(this_day, briefing_date) if this_day else None`
  into the template context.

`overpass/main.py`:

- After collection, before render:

  ```python
  this_day = get_primary_for(today)
  ```

- Pass it into `render_briefing(...)`.

No new config keys. No environment variables. No CLI flags.

## Seed dataset (15 entries)

Spread across the year, each with a `source_url`. Concrete picks (subject to
factual verification while authoring):

| MM-DD | Year | Moment |
|-------|------|--------|
| 01-31 | 2014 | Astralis founding pieces fall into place — Karrigan/dupreeh/dev1ce/Xyp9x at TSM. |
| 02-13 | 2014 | EMS One Katowice (the first CS:GO Major) won by Virtus.pro. |
| 03-04 | 2018 | C9 win ELEAGUE Boston Major. |
| 03-30 | 2014 | CS:GO surpasses 100k concurrent players for the first time. |
| 04-13 | 2024 | Spirit win PGL Major Copenhagen. |
| 05-21 | 2023 | Vitality win BLAST Paris Major (first ZywOo Major). |
| 06-08 | 2014 | dust2 receives its competitive rework. |
| 07-12 | 2015 | ESL One Cologne won by Fnatic — the "boost" Major. |
| 07-22 | 2018 | Astralis win FACEIT London → Intel Grand Slam. |
| 08-21 | 2011 | Counter-Strike: Global Offensive announced by Valve. |
| 09-27 | 2023 | CS2 ships, replaces CS:GO. |
| 10-30 | 2016 | ELEAGUE S2 Major Atlanta won by Astralis (first Major). |
| 11-04 | 2021 | NaVi win PGL Stockholm Major (s1mple's first Major). |
| 11-19 | 2017 | Gambit dynasty era ends after EPICENTER. |
| 12-09 | 2022 | s1mple's record HLTV ratings season closes. |

Final list and copy will be polished during implementation; the table above
demonstrates spread + variety, not a frozen contract.

## Testing

| Test file | What it covers |
|-----------|----------------|
| `tests/test_history_loader.py` | Loads the **real** seed YAML; asserts every bucket parses, has a valid primary, and `MM-DD` keys are real calendar dates. CI-level schema regression guard. |
| `tests/test_history_lookup.py` | Patches `load_history` with a temp dict. Asserts: primary returned for known date; `None` for missing date; year inside the entry doesn't affect lookup. |
| `tests/test_html_delivery.py` | Extend with two cases: (a) renders the history section (headline + narrative + computed date label) when `this_day` is passed; (b) section omitted when not passed. |

No network, no LLM, no Playwright.

## What this design explicitly avoids

- Per-date or per-entry priority scores (Q2 chose explicit primary instead).
- Runtime LLM enrichment of curated copy (Q3 chose pre-written narrative).
- A "rendered something rather than nothing" fallback (Q4 chose omit).
- A second collector or async I/O — this is a synchronous, in-process lookup.
- A separate database or migration — YAML in the repo is the source of truth.

## Open questions

None. All design decisions are locked.
