# Liquipedia client foundation + HLTV-fallback enrichment

**Date:** 2026-04-23
**Status:** Approved (pending user review of written spec)
**Sub-feature:** 1 of 3 in the Liquipedia integration roadmap

## Roadmap context

This is the first of three independent sub-features adding Liquipedia as a
data source. Each ships separately with its own spec → plan → implementation
cycle:

1. **(this spec)** Liquipedia client foundation + HLTV-fallback enrichment.
2. Upcoming matches collector + "Today's Slate" briefing section.
3. Transfers collector + "Transfers" briefing section.

This sub-feature establishes the client, cache, rate limiter, parsers, and
test patterns that the next two will reuse. It changes no briefing UI.

## Cross-cutting decisions (apply to all three sub-features)

|              | Decision                                                                                                 |
| ------------ | -------------------------------------------------------------------------------------------------------- |
| Access       | MediaWiki API only (`action=parse`, `action=opensearch`). LPDB deferred.                                 |
| Politeness   | In-memory async rate limiter + on-disk response cache.                                                   |
| Failure mode | Soft-fail everywhere — log + return empty/None, briefing still renders.                                  |
| Config shape | Single `liquipedia:` block with nested per-feature toggles.                                              |
| User-Agent   | `overpass/0.1.0 (+https://github.com/lindhammer/overpass; 63104033+lindhammer@users.noreply.github.com)` |

## Goal

Add a polite, cached Liquipedia MediaWiki client. Use it in exactly one place:
when `HLTVMatchesCollector._collect_match_detail` raises (e.g. Cloudflare
challenge, malformed score, missing field), fall back to Liquipedia to recover
team scores, maps, and winner. Briefing UI does not change.

## Non-goals

- Upcoming matches / today's slate (sub-feature 2).
- Transfers (sub-feature 3).
- Briefing template changes.
- LPDB integration.
- Replacing successful HLTV match-detail parses with Liquipedia data
  (enrichment of healthy matches is sub-feature 2 territory).
- Liquipedia coverage of news, podcasts, patches.

## Architecture

```
overpass/liquipedia/
├── __init__.py
├── client.py          # LiquipediaClient: httpx + UA + rate limiter + cache
├── cache.py           # FileCache: keyed get/set with TTL on disk
├── ratelimit.py       # AsyncRateLimiter: global min-interval enforcement
├── models.py          # LiquipediaMatch, LiquipediaMap (pydantic)
├── pages.py           # find_match_page(event_name) → page title | None
└── matches.py         # parse_match_from_tournament_page(html, t1, t2) → LiquipediaMatch | None
```

`HLTVMatchesCollector` gains an optional dependency
`liquipedia_client: LiquipediaClient | None`. In `_collect_match_detail`, if
`parse_match_detail` raises and `liquipedia_client is not None`, call a new
private `_fallback_to_liquipedia(listing_item)` returning
`HLTVMatchDetail | None`. On `None`, propagate the original exception so the
match is dropped (current behaviour).

## `LiquipediaClient` API

```python
class LiquipediaClient:
    @classmethod
    def from_config(cls, cfg: LiquipediaConfig) -> "LiquipediaClient": ...

    async def parse_page(self, page_title: str) -> str:
        """Return rendered HTML for a wiki page. Cached + rate-limited."""

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        """MediaWiki opensearch — used to find tournament pages."""

    async def close(self) -> None: ...
```

Internals:

- `httpx.AsyncClient` with the User-Agent string from config.
- Single global `AsyncRateLimiter(min_interval=cfg.min_request_interval_seconds)`
  enforcing ≥2s between requests across all endpoints. One `asyncio.Lock` +
  `last_request_at` monotonic timestamp.
- `FileCache` keyed by `sha1(method + sorted_params)`, stored at
  `{cache_dir}/{key[:2]}/{key}.json` as `{fetched_at_iso, body_text}`. TTL
  check on read; expired entries are ignored, not deleted (deterministic,
  cheap).
- A schema-version constant (`_CACHE_SCHEMA = "v1"`) is included in every
  cache key so a future bump invalidates all entries.

## Match identity matching

When `_fallback_to_liquipedia(listing_item)` runs:

1. `find_match_page(listing_item.event_name)` performs an `opensearch` query.
   Filter results to titles containing a normalized token from the event name
   (case-insensitive substring of the longest token ≥4 chars). Return the
   top remaining hit, or `None`.
2. If a page is found, `client.parse_page(title)` returns the rendered
   tournament HTML.
3. `parse_match_from_tournament_page(html, listing_item.team1_name,
listing_item.team2_name)` walks `<div class="bracket-game">` and
   `<div class="brkts-match">` nodes, normalizes each pair of team names, and
   compares against the listing-item teams using a shared
   `team_name_matches(a, b)` helper:
   - casefold both sides
   - strip common suffixes (`esports`, `gaming`, `team`, leading `team `)
   - exact match after normalization
4. If exactly one node matches both teams, extract `team1_score`,
   `team2_score`, and `maps[]`. If zero or multiple match, return `None`.
5. The collector reconstructs an `HLTVMatchDetail` using listing-item values
   for `event_name`, `format`, `played_at`, and empty lists for `veto` and
   `player_stats` (Liquipedia coverage of those is out of scope here). The
   metadata dict gets `"source_fallback": "liquipedia"` so downstream
   consumers can tell it apart.

## Config additions

`config.yaml`:

```yaml
liquipedia:
  base_url: "https://liquipedia.net/counterstrike"
  api_url: "https://liquipedia.net/counterstrike/api.php"
  contact: "63104033+lindhammer@users.noreply.github.com"
  user_agent: "overpass/0.1.0 (+https://github.com/lindhammer/overpass; {contact})"
  min_request_interval_seconds: 2.0
  request_timeout_seconds: 30
  cache_dir: ".cache/liquipedia"
  cache_ttl_minutes: 30
  hltv_fallback: true
  upcoming_matches:
    enabled: false
    lookahead_hours: 36
  transfers:
    enabled: false
    lookback_hours: 48
```

`overpass/config.py`:

- New `LiquipediaUpcomingConfig` (`enabled: bool`, `lookahead_hours: int`).
- New `LiquipediaTransfersConfig` (`enabled: bool`, `lookback_hours: int`).
- New `LiquipediaConfig` with the fields above plus
  `upcoming_matches: LiquipediaUpcomingConfig` and
  `transfers: LiquipediaTransfersConfig`.
- `AppConfig.liquipedia: LiquipediaConfig = LiquipediaConfig()` so configs
  without the block keep working with defaults (`hltv_fallback=True`).
- `user_agent` is rendered with `{contact}` substituted in a
  `model_validator(mode="after")` so the contact is the single source of
  truth.

`.gitignore`: add `.cache/`.

## Pipeline wiring

`overpass/main.py`:

- Rename `_build_collectors_with_shared_hltv_client` to
  `_build_collectors_with_shared_clients` and have it construct a single
  `LiquipediaClient` when `cfg.liquipedia.hltv_fallback or
cfg.liquipedia.upcoming_matches.enabled or cfg.liquipedia.transfers.enabled`.
- Pass `liquipedia_client` to `HLTVMatchesCollector`.
- Close the Liquipedia client in the same `finally` block that closes the
  HLTV browser client.
- Other collectors are unchanged.

## Failure surface

| Failure                           | Behaviour                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------ |
| Network/HTTP error                | Log warning + return `None`/`[]`. Match is dropped (today's behaviour).        |
| Cache write failure               | Log warning, continue without caching. Never blocks the request.               |
| Concurrent rate-limit overshoot   | Impossible — single global async lock serialises all calls.                    |
| Search returns wrong page         | Page-finder filter rejects mismatched titles → `None`. No false data inserted. |
| Tournament page in unknown layout | Parser returns `None` (no match nodes found). Match dropped.                   |
| Schema-version bump               | All cached entries silently ignored on next read.                              |

## Tests

All sync pytest tests; async functions wrapped with `asyncio.run` inside the
test where needed (the project doesn't use `pytest-asyncio`).

| File                                                       | Coverage                                                                                                                                                                                                                                                                      |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_liquipedia_cache.py`                           | TTL hit/miss/expiry; corrupt file ignored; isolated `tmp_path`.                                                                                                                                                                                                               |
| `tests/test_liquipedia_ratelimit.py`                       | Second call sleeps ≥ interval (fake `time.monotonic`).                                                                                                                                                                                                                        |
| `tests/test_liquipedia_client.py`                          | UA header set; cache hit avoids HTTP call (mocked transport); rate limiter consulted.                                                                                                                                                                                         |
| `tests/test_liquipedia_pages.py`                           | Page-finder picks expected title; rejects when no token match; returns `None` on empty results.                                                                                                                                                                               |
| `tests/test_liquipedia_matches_parser.py`                  | `parse_match_from_tournament_page` against `tests/fixtures/liquipedia_tournament.html` (real captured snippet). Tests: exact match, fuzzy team-name match, zero matches → `None`, multiple matches → `None`.                                                                  |
| `tests/test_hltv_matches_collector_liquipedia_fallback.py` | When `parse_match_detail` raises, the collector calls the (stub) Liquipedia client and emits an `HLTVMatchDetail` derived from it, with `metadata["source_fallback"] == "liquipedia"`. When the stub also returns `None`, the match is dropped (today's behaviour preserved). |
| `tests/test_config.py`                                     | Default `LiquipediaConfig` instantiation; `user_agent` interpolation of `{contact}`.                                                                                                                                                                                          |

No live network calls in any test. Fixtures captured manually once and
committed.

## Risks and mitigations

| Risk                                                                  | Mitigation                                                                                                                                                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tournament-page templates vary (bracket vs group-stage vs matchlist). | Start with `brkts-match` + `bracket-game` selectors only. Parser returns `None` rather than raising on unknown structure. Capture a real fixture before writing the parser; add additional selectors only when a real failure motivates it. |
| Page-finder picks the wrong tournament (e.g. previous season).        | Strict filter — event-name token must appear in the candidate title. On ambiguity, return `None`. Better to drop a match than to inject wrong data.                                                                                         |
| Liquipedia rate-limit terms change.                                   | Settings live in config; bumping `min_request_interval_seconds` is a one-line change.                                                                                                                                                       |
| Cache directory grows unbounded.                                      | TTL is 30 min by default and entries are small; size is self-limiting in practice (a daily run rotates ~10-50 entries). A future cleanup task is out of scope.                                                                              |
| Wikitext/HTML changes in Liquipedia.                                  | Soft-fail policy + parser-level `None` return ensures we degrade gracefully rather than crash.                                                                                                                                              |

## Out of scope (explicit reminders)

- No briefing template changes.
- No new section in the daily briefing.
- No upcoming-matches or transfers logic. The dormant config blocks
  (`upcoming_matches.enabled: false`, `transfers.enabled: false`) exist so
  sub-features 2 and 3 don't have to touch this spec's config schema.
- No team-logo extraction. Crests remain placeholders.
- No retry policy beyond the existing soft-fail; transient HTTP errors
  drop the match for this run.

