# Liquipedia Client + HLTV-Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a polite, cached Liquipedia MediaWiki client and use it to recover HLTV match-detail data when HLTV's parser fails (Cloudflare, malformed scores, missing fields). No briefing UI changes.

**Architecture:** New `overpass/liquipedia/` package with one file per concern: `cache.py` (TTL'd file cache), `ratelimit.py` (global async min-interval), `client.py` (httpx wrapper using both), `pages.py` (event-name → wiki page title via opensearch), `matches.py` (parse a tournament page for a specific match-up), `models.py` (pydantic). `HLTVMatchesCollector` gains an optional `liquipedia_client` dependency and falls back to it when `parse_match_detail` raises. Soft-fail throughout; if Liquipedia can't help either, the match is dropped (current behaviour).

**Tech Stack:** Python 3.12, httpx, pydantic v2, BeautifulSoup4, pytest. No new top-level dependencies.

**Spec:** [`docs/superpowers/specs/2026-04-23-liquipedia-client-and-hltv-fallback-design.md`](../specs/2026-04-23-liquipedia-client-and-hltv-fallback-design.md)

---

## Task 0: Capture real Liquipedia fixtures

Before writing the parser, capture two real pages so we don't write the parser blind. These fixtures back the parser tests in Task 6 and the page-finder test in Task 5.

**Files:**

- Create: `tests/fixtures/liquipedia_tournament.html`
- Create: `tests/fixtures/liquipedia_opensearch.json`

- [ ] **Step 1: Pick a recent tournament page**

Open https://liquipedia.net/counterstrike/Liquipedia:Tournaments in a browser. Pick a tournament that:

- Is currently ongoing or finished within the last 7 days (so the page reflects modern templates)
- Has at least 4 completed matches with maps and scores
- Is at least Tier B so the page is well-maintained

Note the exact page title (e.g. `BetBoom_RUSH_B_Summit/Season_3`).

- [ ] **Step 2: Fetch and save the parsed HTML**

Run from the repo root:

```powershell
$title = "PASTE_TITLE_HERE"
$url = "https://liquipedia.net/counterstrike/api.php?action=parse&page=$title&format=json&prop=text"
$ua = "overpass/0.1.0 (+https://github.com/lindhammer/overpass; 63104033+lindhammer@users.noreply.github.com)"
$json = Invoke-RestMethod -Uri $url -Headers @{ "User-Agent" = $ua }
$json.parse.text."*" | Out-File -FilePath tests/fixtures/liquipedia_tournament.html -Encoding utf8
```

Verify the file is non-empty and contains either `brkts-match` or `bracket-game` substrings:

```powershell
Select-String -Path tests/fixtures/liquipedia_tournament.html -Pattern "brkts-match|bracket-game" | Select-Object -First 3
```

If neither pattern appears, pick a different tournament and repeat.

- [ ] **Step 3: Capture an opensearch response**

```powershell
$query = "BetBoom RUSH B Summit Season 3"   # use the actual event_name string an HLTV listing would produce
$url = "https://liquipedia.net/counterstrike/api.php?action=opensearch&search=$([uri]::EscapeDataString($query))&limit=5&format=json"
$ua = "overpass/0.1.0 (+https://github.com/lindhammer/overpass; 63104033+lindhammer@users.noreply.github.com)"
Invoke-RestMethod -Uri $url -Headers @{ "User-Agent" = $ua } | ConvertTo-Json -Depth 5 | Out-File -FilePath tests/fixtures/liquipedia_opensearch.json -Encoding utf8
```

Open `tests/fixtures/liquipedia_opensearch.json`. The MediaWiki opensearch response is an array of four arrays: `[query, [titles], [descriptions], [urls]]`. Confirm `[titles]` (the second element) contains at least one entry that includes a recognisable token from your event name.

- [ ] **Step 4: Identify two real match-ups in the tournament HTML**

Open `tests/fixtures/liquipedia_tournament.html` in an editor. Find one completed match. Note:

- `team1_name` exactly as it appears in HLTV listings (use HLTV's spelling)
- `team2_name` exactly as it appears on Liquipedia
- expected `team1_score` / `team2_score`
- expected map list `[(map_name, t1, t2), ...]`

Record these four facts in a comment at the top of `tests/test_liquipedia_matches_parser.py` when you create that file in Task 6. They define the test expectations.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/liquipedia_tournament.html tests/fixtures/liquipedia_opensearch.json
git commit -m "test: capture Liquipedia tournament + opensearch fixtures"
```

---

## Task 1: `LiquipediaConfig` pydantic models

**Files:**

- Modify: `overpass/config.py`
- Modify: `config.yaml`
- Modify: `.gitignore`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_liquipedia_config_defaults():
    from overpass.config import LiquipediaConfig

    cfg = LiquipediaConfig()
    assert cfg.base_url == "https://liquipedia.net/counterstrike"
    assert cfg.api_url == "https://liquipedia.net/counterstrike/api.php"
    assert cfg.min_request_interval_seconds == 2.0
    assert cfg.cache_ttl_minutes == 30
    assert cfg.hltv_fallback is True
    assert cfg.upcoming_matches.enabled is False
    assert cfg.upcoming_matches.lookahead_hours == 36
    assert cfg.transfers.enabled is False
    assert cfg.transfers.lookback_hours == 48


def test_liquipedia_user_agent_interpolates_contact():
    from overpass.config import LiquipediaConfig

    cfg = LiquipediaConfig(
        contact="me@example.com",
        user_agent="overpass/0.1.0 (+url; {contact})",
    )
    assert cfg.user_agent == "overpass/0.1.0 (+url; me@example.com)"


def test_app_config_includes_liquipedia_block():
    from overpass.config import AppConfig

    cfg = AppConfig()
    assert cfg.liquipedia.hltv_fallback is True
```

- [ ] **Step 2: Run tests — expect ImportError / AttributeError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -q
```

Expected: failures importing `LiquipediaConfig` from `overpass.config`.

- [ ] **Step 3: Add `LiquipediaConfig` and friends to `overpass/config.py`**

Insert after the existing `LLMConfig` class (above `TelegramConfig`):

```python
class LiquipediaUpcomingConfig(BaseModel):
    enabled: bool = False
    lookahead_hours: int = Field(default=36, gt=0)


class LiquipediaTransfersConfig(BaseModel):
    enabled: bool = False
    lookback_hours: int = Field(default=48, gt=0)


class LiquipediaConfig(BaseModel):
    base_url: str = "https://liquipedia.net/counterstrike"
    api_url: str = "https://liquipedia.net/counterstrike/api.php"
    contact: str = "63104033+lindhammer@users.noreply.github.com"
    user_agent: str = (
        "overpass/0.1.0 (+https://github.com/lindhammer/overpass; {contact})"
    )
    min_request_interval_seconds: float = Field(default=2.0, ge=0)
    request_timeout_seconds: int = Field(default=30, gt=0)
    cache_dir: str = ".cache/liquipedia"
    cache_ttl_minutes: int = Field(default=30, ge=0)
    hltv_fallback: bool = True
    upcoming_matches: LiquipediaUpcomingConfig = LiquipediaUpcomingConfig()
    transfers: LiquipediaTransfersConfig = LiquipediaTransfersConfig()

    def model_post_init(self, __context: Any) -> None:
        if "{contact}" in self.user_agent:
            object.__setattr__(self, "user_agent", self.user_agent.format(contact=self.contact))
```

Add `liquipedia: LiquipediaConfig = LiquipediaConfig()` to the `AppConfig` field list (alongside `llm`).

- [ ] **Step 4: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -q
```

- [ ] **Step 5: Add the YAML block**

Append to `config.yaml`:

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

- [ ] **Step 6: Add `.cache/` to `.gitignore`**

Append to `.gitignore`:

```
.cache/
```

- [ ] **Step 7: Smoke-test config load**

```powershell
.venv\Scripts\python.exe -c "from overpass.config import load_config; c = load_config(); print(c.liquipedia.user_agent); print(c.liquipedia.hltv_fallback)"
```

Expected: prints the rendered UA string with the email substituted, then `True`.

- [ ] **Step 8: Commit**

```powershell
git add overpass/config.py config.yaml .gitignore tests/test_config.py
git commit -m "feat(config): add Liquipedia configuration block"
```

---

## Task 2: `FileCache` with TTL

**Files:**

- Create: `overpass/liquipedia/__init__.py` (empty)
- Create: `overpass/liquipedia/cache.py`
- Test: `tests/test_liquipedia_cache.py`

- [ ] **Step 1: Create the empty package init**

Create `overpass/liquipedia/__init__.py` containing only:

```python
"""Liquipedia MediaWiki client and parsers."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_liquipedia_cache.py`:

```python
"""FileCache tests — TTL hit/miss/expiry, corruption tolerance."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from overpass.liquipedia.cache import FileCache


def test_get_returns_none_when_key_missing(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    assert cache.get("nope") is None


def test_set_then_get_returns_value(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("k", "hello")
    assert cache.get("k") == "hello"


def test_get_returns_none_when_entry_expired(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=0)
    cache.set("k", "hello")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_get_returns_none_for_corrupt_file(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    # Force a corrupt entry at the path FileCache would use.
    cache.set("k", "hello")
    cache_file = next(tmp_path.rglob("*.json"))
    cache_file.write_text("not json", encoding="utf-8")
    assert cache.get("k") is None


def test_set_handles_unwritable_directory_silently(tmp_path: Path, monkeypatch) -> None:
    # Simulate a write failure: replace Path.write_text with one that raises.
    cache = FileCache(tmp_path, ttl_seconds=60)
    real_write_text = Path.write_text

    def boom(self, *a, **kw):
        if "liquipedia" in str(self) or self.suffix == ".json":
            raise OSError("disk full")
        return real_write_text(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", boom)
    # Must not raise.
    cache.set("k", "hello")


def test_keys_are_sharded_by_prefix(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("alpha", "a")
    cache.set("beta", "b")
    # Each value lives in a 2-char shard subdir named after the SHA-1 prefix.
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 2
    for f in files:
        assert f.parent.name == f.stem[:2]
```

- [ ] **Step 3: Run tests — expect ImportError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_cache.py -q
```

- [ ] **Step 4: Implement `FileCache`**

Create `overpass/liquipedia/cache.py`:

```python
"""On-disk TTL cache for Liquipedia API responses."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("overpass.liquipedia.cache")

_CACHE_SCHEMA = "v1"


class FileCache:
    """SHA-1-keyed file cache with a single TTL applied to every entry.

    Entries live at ``{root}/{key[:2]}/{key}.json`` and store
    ``{"fetched_at": float_unix, "body": str}``. Expired entries are
    ignored on read (not deleted) so the cache is deterministic and
    cheap. Write failures are logged and swallowed — the cache is a
    performance aid, never a correctness boundary.
    """

    def __init__(self, root: Path, ttl_seconds: float) -> None:
        self._root = Path(root)
        self._ttl = float(ttl_seconds)

    def _key_for(self, raw_key: str) -> str:
        digest = hashlib.sha1(f"{_CACHE_SCHEMA}:{raw_key}".encode("utf-8")).hexdigest()
        return digest

    def _path_for(self, raw_key: str) -> Path:
        key = self._key_for(raw_key)
        return self._root / key[:2] / f"{key}.json"

    def get(self, raw_key: str) -> str | None:
        path = self._path_for(raw_key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(payload["fetched_at"])
            body = payload["body"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if time.time() - fetched_at > self._ttl:
            return None
        return body

    def set(self, raw_key: str, body: str) -> None:
        path = self._path_for(raw_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"fetched_at": time.time(), "body": body}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write cache entry %s: %s", path, exc)
```

- [ ] **Step 5: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_cache.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add overpass/liquipedia/__init__.py overpass/liquipedia/cache.py tests/test_liquipedia_cache.py
git commit -m "feat(liquipedia): add TTL'd FileCache"
```

---

## Task 3: `AsyncRateLimiter`

**Files:**

- Create: `overpass/liquipedia/ratelimit.py`
- Test: `tests/test_liquipedia_ratelimit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_liquipedia_ratelimit.py`:

```python
"""AsyncRateLimiter tests — enforces global min-interval, no overshoot."""

from __future__ import annotations

import asyncio

import pytest

from overpass.liquipedia.ratelimit import AsyncRateLimiter


def test_first_call_does_not_wait() -> None:
    limiter = AsyncRateLimiter(min_interval=0.05)
    elapsed = asyncio.run(_timed(limiter))
    assert elapsed < 0.04


def test_second_call_waits_at_least_interval() -> None:
    limiter = AsyncRateLimiter(min_interval=0.05)

    async def two_calls() -> float:
        loop = asyncio.get_event_loop()
        await limiter.acquire()
        start = loop.time()
        await limiter.acquire()
        return loop.time() - start

    elapsed = asyncio.run(two_calls())
    assert elapsed >= 0.045  # small clock slack


def test_concurrent_calls_are_serialised() -> None:
    limiter = AsyncRateLimiter(min_interval=0.03)

    async def run() -> list[float]:
        loop = asyncio.get_event_loop()
        timestamps: list[float] = []

        async def one() -> None:
            await limiter.acquire()
            timestamps.append(loop.time())

        await asyncio.gather(one(), one(), one())
        return timestamps

    ts = asyncio.run(run())
    ts.sort()
    # Each consecutive pair must be at least min_interval apart.
    assert ts[1] - ts[0] >= 0.025
    assert ts[2] - ts[1] >= 0.025


async def _timed(limiter: AsyncRateLimiter) -> float:
    loop = asyncio.get_event_loop()
    start = loop.time()
    await limiter.acquire()
    return loop.time() - start
```

- [ ] **Step 2: Run tests — expect ImportError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_ratelimit.py -q
```

- [ ] **Step 3: Implement `AsyncRateLimiter`**

Create `overpass/liquipedia/ratelimit.py`:

```python
"""Global async rate limiter — enforces a minimum interval between calls."""

from __future__ import annotations

import asyncio


class AsyncRateLimiter:
    """Serialises calls so consecutive ``acquire()`` invocations are at
    least ``min_interval`` seconds apart, regardless of concurrency."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = float(min_interval)
        self._lock = asyncio.Lock()
        self._last_at: float | None = None

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            if self._last_at is not None:
                wait = self._min_interval - (loop.time() - self._last_at)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_at = loop.time()
```

- [ ] **Step 4: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_ratelimit.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add overpass/liquipedia/ratelimit.py tests/test_liquipedia_ratelimit.py
git commit -m "feat(liquipedia): add AsyncRateLimiter"
```

---

## Task 4: `LiquipediaClient`

**Files:**

- Create: `overpass/liquipedia/client.py`
- Test: `tests/test_liquipedia_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_liquipedia_client.py`:

```python
"""LiquipediaClient tests — UA header, cache use, rate-limit consultation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from overpass.config import LiquipediaConfig
from overpass.liquipedia.client import LiquipediaClient


def _make_client(tmp_path: Path, transport: httpx.MockTransport) -> LiquipediaClient:
    cfg = LiquipediaConfig(
        cache_dir=str(tmp_path),
        cache_ttl_minutes=60,
        min_request_interval_seconds=0.0,  # speed up tests
    )
    return LiquipediaClient.from_config(cfg, transport=transport)


def test_parse_page_sends_user_agent_header(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["user-agent"]
        return httpx.Response(
            200,
            json={"parse": {"text": {"*": "<div>hello</div>"}}},
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        body = asyncio.run(client.parse_page("Some_Page"))
    finally:
        asyncio.run(client.close())
    assert body == "<div>hello</div>"
    assert "overpass/" in captured["ua"]
    assert "63104033+lindhammer@users.noreply.github.com" in captured["ua"]


def test_parse_page_caches_response(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"parse": {"text": {"*": "<div>cached</div>"}}},
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        a = asyncio.run(client.parse_page("Page"))
        b = asyncio.run(client.parse_page("Page"))
    finally:
        asyncio.run(client.close())
    assert a == b == "<div>cached</div>"
    assert calls["n"] == 1


def test_search_page_titles_returns_titles_array(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=["BetBoom RUSH B Summit Season 3", ["Title A", "Title B"], ["", ""], ["", ""]],
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        titles = asyncio.run(client.search_page_titles("BetBoom"))
    finally:
        asyncio.run(client.close())
    assert titles == ["Title A", "Title B"]


def test_parse_page_returns_empty_string_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        body = asyncio.run(client.parse_page("Page"))
    finally:
        asyncio.run(client.close())
    assert body == ""


def test_search_returns_empty_list_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        titles = asyncio.run(client.search_page_titles("anything"))
    finally:
        asyncio.run(client.close())
    assert titles == []
```

- [ ] **Step 2: Run tests — expect ImportError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_client.py -q
```

- [ ] **Step 3: Implement `LiquipediaClient`**

Create `overpass/liquipedia/client.py`:

```python
"""Liquipedia MediaWiki client — UA, rate-limited, cached."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from overpass.config import LiquipediaConfig
from overpass.liquipedia.cache import FileCache
from overpass.liquipedia.ratelimit import AsyncRateLimiter

logger = logging.getLogger("overpass.liquipedia.client")


class LiquipediaClient:
    """Polite, cached MediaWiki client for Liquipedia.

    Soft-fails on HTTP and parse errors — callers receive empty results
    so the surrounding pipeline degrades gracefully.
    """

    def __init__(
        self,
        api_url: str,
        user_agent: str,
        request_timeout_seconds: int,
        cache: FileCache,
        rate_limiter: AsyncRateLimiter,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url
        self._cache = cache
        self._rate_limiter = rate_limiter
        client_kwargs: dict = {
            "headers": {"User-Agent": user_agent},
            "timeout": request_timeout_seconds,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**client_kwargs)

    @classmethod
    def from_config(
        cls,
        cfg: LiquipediaConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "LiquipediaClient":
        cache = FileCache(
            root=Path(cfg.cache_dir),
            ttl_seconds=cfg.cache_ttl_minutes * 60,
        )
        limiter = AsyncRateLimiter(min_interval=cfg.min_request_interval_seconds)
        return cls(
            api_url=cfg.api_url,
            user_agent=cfg.user_agent,
            request_timeout_seconds=cfg.request_timeout_seconds,
            cache=cache,
            rate_limiter=limiter,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def parse_page(self, page_title: str) -> str:
        """Return rendered HTML for a wiki page, or "" on any failure."""
        cache_key = f"parse:{page_title}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "action": "parse",
            "page": page_title,
            "format": "json",
            "prop": "text",
        }
        body = await self._fetch_json(params)
        if not body:
            return ""
        try:
            html = body["parse"]["text"]["*"]
        except (KeyError, TypeError):
            logger.warning("Unexpected Liquipedia parse response for %s", page_title)
            return ""
        self._cache.set(cache_key, html)
        return html

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        """Return opensearch title suggestions, or [] on any failure."""
        cache_key = f"opensearch:{query}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass

        params = {
            "action": "opensearch",
            "search": query,
            "limit": str(limit),
            "format": "json",
        }
        body = await self._fetch_json(params)
        if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
            return []
        titles = [t for t in body[1] if isinstance(t, str)]
        self._cache.set(cache_key, json.dumps(titles))
        return titles

    async def _fetch_json(self, params: dict[str, str]):
        await self._rate_limiter.acquire()
        try:
            resp = await self._client.get(self._api_url, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Liquipedia request failed (%s): %s", params.get("action"), exc)
            return None
```

- [ ] **Step 4: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_client.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add overpass/liquipedia/client.py tests/test_liquipedia_client.py
git commit -m "feat(liquipedia): add LiquipediaClient (UA, cache, rate-limit)"
```

---

## Task 5: Page-finder

**Files:**

- Create: `overpass/liquipedia/pages.py`
- Test: `tests/test_liquipedia_pages.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_liquipedia_pages.py`:

```python
"""Page-finder tests — token filter, soft-fail on no matches."""

from __future__ import annotations

import asyncio

import pytest

from overpass.liquipedia.pages import find_match_page


class _StubClient:
    def __init__(self, titles: list[str]) -> None:
        self._titles = titles
        self.queries: list[str] = []

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        self.queries.append(query)
        return self._titles


def test_find_match_page_returns_first_token_matching_title() -> None:
    client = _StubClient(
        titles=[
            "Some Other Tournament",
            "BetBoom RUSH B Summit/Season 3",
            "BetBoom RUSH B Summit/Season 2",
        ]
    )
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result == "BetBoom RUSH B Summit/Season 3"


def test_find_match_page_returns_none_when_no_titles_match_token() -> None:
    client = _StubClient(titles=["Unrelated Page", "Another Thing"])
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result is None


def test_find_match_page_returns_none_on_empty_results() -> None:
    client = _StubClient(titles=[])
    result = asyncio.run(find_match_page(client, "Anything"))
    assert result is None


def test_find_match_page_returns_none_for_empty_event_name() -> None:
    client = _StubClient(titles=["Whatever"])
    result = asyncio.run(find_match_page(client, ""))
    assert result is None
    assert client.queries == []  # no API call made


def test_find_match_page_token_match_is_case_insensitive() -> None:
    client = _StubClient(titles=["betboom rush b summit/season 3"])
    result = asyncio.run(find_match_page(client, "BetBoom RUSH B Summit Season 3"))
    assert result == "betboom rush b summit/season 3"
```

- [ ] **Step 2: Run tests — expect ImportError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_pages.py -q
```

- [ ] **Step 3: Implement `find_match_page`**

Create `overpass/liquipedia/pages.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_pages.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add overpass/liquipedia/pages.py tests/test_liquipedia_pages.py
git commit -m "feat(liquipedia): add page-finder with token-match filter"
```

---

## Task 6: Tournament-page match parser

**Files:**

- Create: `overpass/liquipedia/models.py`
- Create: `overpass/liquipedia/matches.py`
- Test: `tests/test_liquipedia_matches_parser.py`

> **IMPORTANT:** Task 0 must be complete. This task's tests reference `tests/fixtures/liquipedia_tournament.html` and the four facts you recorded about a real match-up.

- [ ] **Step 1: Define the result model**

Create `overpass/liquipedia/models.py`:

```python
"""Structured result models for Liquipedia parsers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiquipediaMap(BaseModel):
    name: str
    team1_score: int
    team2_score: int


class LiquipediaMatch(BaseModel):
    team1_name: str
    team2_name: str
    team1_score: int
    team2_score: int
    winner_name: str | None = None
    maps: list[LiquipediaMap] = Field(default_factory=list)
```

- [ ] **Step 2: Write the failing parser tests**

Create `tests/test_liquipedia_matches_parser.py` and substitute the real values you recorded in Task 0 Step 4 for `EXPECTED_*`:

```python
"""parse_match_from_tournament_page tests against a real captured fixture.

Fixture: tests/fixtures/liquipedia_tournament.html
Recorded match-up (from Task 0 Step 4):
  team1_name (HLTV spelling): EXPECTED_TEAM1
  team2_name (Liquipedia spelling): EXPECTED_TEAM2
  expected score: EXPECTED_T1_SCORE - EXPECTED_T2_SCORE
  expected maps: EXPECTED_MAPS  # e.g. [("Nuke", 13, 1), ("Mirage", 13, 3)]
"""

from __future__ import annotations

from pathlib import Path

from overpass.liquipedia.matches import parse_match_from_tournament_page

# REPLACE these with the values recorded in Task 0 Step 4.
EXPECTED_TEAM1 = "Legacy"
EXPECTED_TEAM2 = "ALZON"
EXPECTED_T1_SCORE = 2
EXPECTED_T2_SCORE = 0
EXPECTED_MAPS = [("Nuke", 13, 1), ("Mirage", 13, 3)]

_FIXTURE = Path(__file__).parent / "fixtures" / "liquipedia_tournament.html"


def _html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_parser_finds_known_matchup() -> None:
    match = parse_match_from_tournament_page(_html(), EXPECTED_TEAM1, EXPECTED_TEAM2)
    assert match is not None
    assert match.team1_score == EXPECTED_T1_SCORE
    assert match.team2_score == EXPECTED_T2_SCORE
    assert [(m.name, m.team1_score, m.team2_score) for m in match.maps] == EXPECTED_MAPS


def test_parser_normalises_team_name_suffixes() -> None:
    # Same matchup, but with a "Team " prefix that should normalise away.
    match = parse_match_from_tournament_page(
        _html(), f"Team {EXPECTED_TEAM1}", EXPECTED_TEAM2
    )
    assert match is not None
    assert match.team1_score == EXPECTED_T1_SCORE


def test_parser_returns_none_when_no_match_found() -> None:
    match = parse_match_from_tournament_page(_html(), "Nonexistent A", "Nonexistent B")
    assert match is None


def test_parser_returns_none_when_html_has_no_match_nodes() -> None:
    match = parse_match_from_tournament_page("<html><body>nothing</body></html>", "A", "B")
    assert match is None
```

- [ ] **Step 3: Run tests — expect ImportError**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_matches_parser.py -q
```

- [ ] **Step 4: Implement the parser**

Create `overpass/liquipedia/matches.py`:

```python
"""Parse a Liquipedia tournament page for a specific matchup."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from overpass.liquipedia.models import LiquipediaMap, LiquipediaMatch

logger = logging.getLogger("overpass.liquipedia.matches")

_MATCH_NODE_SELECTORS = ".brkts-match, .bracket-game, .matchlist .match-row"
_TEAM_NAME_SELECTORS = ".name, .team-template-text, .team-template-team-short, .team-template-team2-short"
_SCORE_SELECTORS = ".score, .brkts-opponent-score-inner, .brkts-opponent-score"
_MAP_NODE_SELECTORS = ".brkts-popup-body-game, .bracket-popup-body-element"
_MAP_NAME_SELECTORS = ".brkts-popup-body-game-mapname, .bracket-popup-game-map"
_MAP_SCORE_PATTERN = re.compile(r"(\d+)\s*[-:\u2013]\s*(\d+)")
_SUFFIXES_TO_STRIP = ("esports", "gaming", "team", "club")


def parse_match_from_tournament_page(
    html: str, team1_name: str, team2_name: str
) -> LiquipediaMatch | None:
    """Return the unique matchup of (team1, team2) on this page, or None."""
    if not html or not team1_name or not team2_name:
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[LiquipediaMatch] = []

    for node in soup.select(_MATCH_NODE_SELECTORS):
        match = _parse_match_node(node)
        if match is None:
            continue
        if not _matches_pair(match, team1_name, team2_name):
            continue
        # Orient the match so team1 in the result corresponds to the requested team1.
        oriented = _orient_to(match, team1_name)
        candidates.append(oriented)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            "Ambiguous Liquipedia match for %s vs %s (%d candidates)",
            team1_name, team2_name, len(candidates),
        )
    return None


def _parse_match_node(node: Tag) -> LiquipediaMatch | None:
    name_nodes = node.select(_TEAM_NAME_SELECTORS)
    score_nodes = node.select(_SCORE_SELECTORS)
    if len(name_nodes) < 2 or len(score_nodes) < 2:
        return None

    raw_t1 = _clean(name_nodes[0].get_text(" ", strip=True))
    raw_t2 = _clean(name_nodes[1].get_text(" ", strip=True))
    if not raw_t1 or not raw_t2:
        return None

    try:
        s1 = int(_clean(score_nodes[0].get_text(" ", strip=True)))
        s2 = int(_clean(score_nodes[1].get_text(" ", strip=True)))
    except ValueError:
        return None

    maps = _parse_maps(node)
    winner = raw_t1 if s1 > s2 else raw_t2 if s2 > s1 else None

    return LiquipediaMatch(
        team1_name=raw_t1,
        team2_name=raw_t2,
        team1_score=s1,
        team2_score=s2,
        winner_name=winner,
        maps=maps,
    )


def _parse_maps(node: Tag) -> list[LiquipediaMap]:
    maps: list[LiquipediaMap] = []
    for map_node in node.select(_MAP_NODE_SELECTORS):
        name_node = map_node.select_one(_MAP_NAME_SELECTORS)
        if name_node is None:
            continue
        name = _clean(name_node.get_text(" ", strip=True))
        text = _clean(map_node.get_text(" ", strip=True))
        m = _MAP_SCORE_PATTERN.search(text)
        if not name or m is None:
            continue
        maps.append(LiquipediaMap(name=name, team1_score=int(m.group(1)), team2_score=int(m.group(2))))
    return maps


def _matches_pair(match: LiquipediaMatch, want_t1: str, want_t2: str) -> bool:
    a = _normalize(match.team1_name)
    b = _normalize(match.team2_name)
    x = _normalize(want_t1)
    y = _normalize(want_t2)
    return {a, b} == {x, y}


def _orient_to(match: LiquipediaMatch, want_t1: str) -> LiquipediaMatch:
    if _normalize(match.team1_name) == _normalize(want_t1):
        return match
    return LiquipediaMatch(
        team1_name=match.team2_name,
        team2_name=match.team1_name,
        team1_score=match.team2_score,
        team2_score=match.team1_score,
        winner_name=match.winner_name,
        maps=[
            LiquipediaMap(name=m.name, team1_score=m.team2_score, team2_score=m.team1_score)
            for m in match.maps
        ],
    )


def _normalize(name: str) -> str:
    n = name.casefold().strip()
    if n.startswith("team "):
        n = n[5:]
    for suffix in _SUFFIXES_TO_STRIP:
        if n.endswith(f" {suffix}"):
            n = n[: -(len(suffix) + 1)]
    return n.strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
```

- [ ] **Step 5: Run tests — expect PASS, fix selectors if not**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_liquipedia_matches_parser.py -q -v
```

If `test_parser_finds_known_matchup` fails, open `tests/fixtures/liquipedia_tournament.html`, find the actual class names used for match nodes, team names, scores, and maps in your captured page, and update the `_*_SELECTORS` constants accordingly. Re-run after each adjustment until all four tests pass.

- [ ] **Step 6: Commit**

```powershell
git add overpass/liquipedia/models.py overpass/liquipedia/matches.py tests/test_liquipedia_matches_parser.py
git commit -m "feat(liquipedia): parse a specific matchup from a tournament page"
```

---

## Task 7: HLTV-fallback wiring

**Files:**

- Modify: `overpass/collectors/hltv_matches.py`
- Test: `tests/test_hltv_matches_collector_liquipedia_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hltv_matches_collector_liquipedia_fallback.py`:

```python
"""HLTVMatchesCollector falls back to Liquipedia when match-detail parsing fails."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from overpass.collectors.hltv_matches import HLTVMatchesCollector
from overpass.hltv.models import HLTVMatchResult
from overpass.liquipedia.models import LiquipediaMap, LiquipediaMatch


def _listing_item() -> HLTVMatchResult:
    return HLTVMatchResult(
        external_id="123",
        url="https://www.hltv.org/matches/123/x-vs-y",
        team1_name="Legacy",
        team2_name="ALZON",
        team1_score=0,  # bogus listing scores; detail parse should overwrite
        team2_score=0,
        event_name="BetBoom RUSH B Summit Season 3",
        format="bo3",
        played_at=datetime(2026, 4, 23, 4, 25, tzinfo=timezone.utc),
    )


class _StubLiquipediaClient:
    def __init__(self, match: LiquipediaMatch | None) -> None:
        self._match = match

    async def parse_page(self, page_title: str) -> str:
        return "<html><body>stub</body></html>"

    async def search_page_titles(self, query: str, limit: int = 5) -> list[str]:
        return ["BetBoom RUSH B Summit/Season 3"]

    async def close(self) -> None:
        pass


def _stub_browser_client():
    client = AsyncMock()
    client.fetch_page_content = AsyncMock(return_value="<html>broken</html>")
    client.base_url = "https://www.hltv.org"
    client.headless = True
    client.close = AsyncMock()
    return client


def test_collector_uses_liquipedia_when_hltv_detail_parse_fails() -> None:
    listing = _listing_item()
    fallback_match = LiquipediaMatch(
        team1_name="Legacy",
        team2_name="ALZON",
        team1_score=2,
        team2_score=0,
        winner_name="Legacy",
        maps=[
            LiquipediaMap(name="Nuke", team1_score=13, team2_score=1),
            LiquipediaMap(name="Mirage", team1_score=13, team2_score=3),
        ],
    )
    liq_client = _StubLiquipediaClient(fallback_match)

    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=liq_client,
    )

    with patch(
        "overpass.collectors.hltv_matches.parse_match_from_tournament_page",
        return_value=fallback_match,
    ), patch(
        "overpass.collectors.hltv_matches.find_match_page",
        new=AsyncMock(return_value="BetBoom RUSH B Summit/Season 3"),
    ):
        detail = asyncio.run(collector._collect_match_detail(listing))

    assert detail.team1_score == 2
    assert detail.team2_score == 0
    assert [m.name for m in detail.maps] == ["Nuke", "Mirage"]


def test_collector_drops_match_when_liquipedia_also_fails() -> None:
    listing = _listing_item()
    liq_client = _StubLiquipediaClient(None)

    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=liq_client,
    )

    with patch(
        "overpass.collectors.hltv_matches.find_match_page",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(Exception):
            asyncio.run(collector._collect_match_detail(listing))


def test_collector_without_liquipedia_client_raises_as_today() -> None:
    listing = _listing_item()
    collector = HLTVMatchesCollector(
        browser_client=_stub_browser_client(),
        liquipedia_client=None,
    )
    with pytest.raises(Exception):
        asyncio.run(collector._collect_match_detail(listing))
```

- [ ] **Step 2: Run tests — expect failures**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_hltv_matches_collector_liquipedia_fallback.py -q
```

Expected: TypeError on the `liquipedia_client=` kwarg, plus the fallback tests fail because the production code doesn't call Liquipedia yet.

- [ ] **Step 3: Modify `HLTVMatchesCollector`**

In `overpass/collectors/hltv_matches.py`:

(a) Add imports at the top of the file (next to the existing imports):

```python
from overpass.hltv.models import HLTVMatchDetail, HLTVMatchMapResult, HLTVMatchResult
from overpass.liquipedia.client import LiquipediaClient
from overpass.liquipedia.matches import parse_match_from_tournament_page
from overpass.liquipedia.models import LiquipediaMatch
from overpass.liquipedia.pages import find_match_page
```

(Adjust the `HLTVMatchDetail` import line to include `HLTVMatchMapResult` if not already imported; check the existing import block first.)

(b) Add `liquipedia_client` to `__init__`:

```python
    def __init__(
        self,
        browser_client: HLTVBrowserClient | None = None,
        now: Callable[[], datetime] | None = None,
        base_url: str = "https://www.hltv.org",
        liquipedia_client: LiquipediaClient | None = None,
    ) -> None:
        ...
        self._liquipedia_client = liquipedia_client
        super().__init__()
```

(c) Replace the tail of `_collect_match_detail` so that after the existing HLTV retry attempts exhaust, we try Liquipedia before giving up. Locate the existing method ending in:

```python
        try:
            headful_detail_html = await self._fetch_with_load_fallback(headful_client, listing_item.url)
            return parse_match_detail(
                headful_detail_html,
                listing_item=listing_item,
                base_url=self._base_url,
            )
        finally:
            await headful_client.close()
```

Wrap the headful attempt in a try/except that on `ValueError` (or any `Exception`) attempts Liquipedia. The full replacement for `_collect_match_detail` becomes:

```python
    async def _collect_match_detail(self, listing_item: HLTVMatchResult) -> HLTVMatchDetail:
        detail_html = await self._browser_client.fetch_page_content(listing_item.url)
        try:
            return parse_match_detail(
                detail_html,
                listing_item=listing_item,
                base_url=self._base_url,
            )
        except ValueError as first_error:
            try:
                headless_detail_html = await self._fetch_with_load_fallback(
                    self._browser_client, listing_item.url
                )
                return parse_match_detail(
                    headless_detail_html,
                    listing_item=listing_item,
                    base_url=self._base_url,
                )
            except ValueError:
                if not getattr(self._browser_client, "headless", False):
                    return await self._maybe_fallback_or_raise(listing_item, first_error)

        headful_client = HLTVBrowserClient(
            base_url=self._base_url,
            headless=False,
            request_timeout_seconds=self._hltv_config.request_timeout_seconds,
            min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
        )
        try:
            try:
                headful_detail_html = await self._fetch_with_load_fallback(headful_client, listing_item.url)
                return parse_match_detail(
                    headful_detail_html,
                    listing_item=listing_item,
                    base_url=self._base_url,
                )
            except ValueError as headful_error:
                return await self._maybe_fallback_or_raise(listing_item, headful_error)
        finally:
            await headful_client.close()

    async def _maybe_fallback_or_raise(
        self,
        listing_item: HLTVMatchResult,
        original_error: BaseException,
    ) -> HLTVMatchDetail:
        if self._liquipedia_client is None:
            raise original_error

        try:
            page_title = await find_match_page(self._liquipedia_client, listing_item.event_name or "")
            if page_title is None:
                raise original_error

            html = await self._liquipedia_client.parse_page(page_title)
            if not html:
                raise original_error

            liq_match = parse_match_from_tournament_page(
                html, listing_item.team1_name, listing_item.team2_name
            )
            if liq_match is None:
                raise original_error

            return self._liquipedia_match_to_hltv_detail(listing_item, liq_match)
        except Exception:
            self.logger.exception(
                "Liquipedia fallback failed for %s; dropping match",
                listing_item.url,
            )
            raise original_error from None

    @staticmethod
    def _liquipedia_match_to_hltv_detail(
        listing_item: HLTVMatchResult,
        liq_match: LiquipediaMatch,
    ) -> HLTVMatchDetail:
        return HLTVMatchDetail(
            external_id=listing_item.external_id,
            url=listing_item.url,
            team1_name=listing_item.team1_name,
            team2_name=listing_item.team2_name,
            team1_rank=listing_item.team1_rank,
            team2_rank=listing_item.team2_rank,
            team1_score=liq_match.team1_score,
            team2_score=liq_match.team2_score,
            winner_name=liq_match.winner_name,
            event_name=listing_item.event_name,
            format=listing_item.format,
            played_at=listing_item.played_at,
            maps=[
                HLTVMatchMapResult(
                    name=m.name,
                    team1_score=m.team1_score,
                    team2_score=m.team2_score,
                    winner_name=(
                        listing_item.team1_name if m.team1_score > m.team2_score
                        else listing_item.team2_name if m.team2_score > m.team1_score
                        else None
                    ),
                )
                for m in liq_match.maps
            ],
        )
```

Then add a metadata marker so the existing `_to_collector_item` includes it. Locate `_to_collector_item` and ensure the metadata dict includes:

```python
        metadata = {
            ...
            "source_fallback": "liquipedia"
                if getattr(match, "_source_fallback", None) == "liquipedia"
                else None,
        }
```

If the simpler approach of carrying a sentinel through `HLTVMatchDetail` is too invasive, drop the metadata marker — the spec mentions it as "so downstream consumers can tell it apart" but no current consumer uses it. Skip the marker if it would require model changes; the test for it is not present in this plan.

- [ ] **Step 4: Run tests — expect PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_hltv_matches_collector_liquipedia_fallback.py -q -v
```

- [ ] **Step 5: Run full sync test suite to confirm no regression**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_liquipedia_cache.py tests/test_liquipedia_ratelimit.py tests/test_liquipedia_client.py tests/test_liquipedia_pages.py tests/test_liquipedia_matches_parser.py tests/test_hltv_matches_collector_liquipedia_fallback.py tests/test_hltv_matches_parser.py tests/test_hltv_news_parser.py tests/test_html_delivery.py -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add overpass/collectors/hltv_matches.py tests/test_hltv_matches_collector_liquipedia_fallback.py
git commit -m "feat(hltv): fall back to Liquipedia when match-detail parse fails"
```

---

## Task 8: Pipeline wiring in `main.py`

**Files:**

- Modify: `overpass/main.py`

- [ ] **Step 1: Read the current builder**

Open `overpass/main.py`. Locate `_build_collectors_with_shared_hltv_client`.

- [ ] **Step 2: Add Liquipedia client construction**

Add an import near the top:

```python
from overpass.liquipedia.client import LiquipediaClient
```

Modify `_build_collectors_with_shared_hltv_client` to also build a Liquipedia client when any feature needs it, and pass it to `HLTVMatchesCollector`:

```python
def _build_collectors_with_shared_hltv_client() -> tuple[
    list[BaseCollector], HLTVBrowserClient, LiquipediaClient | None
]:
    config = load_config()
    hltv_browser_client = HLTVBrowserClient.from_config(config.hltv)

    liq_cfg = config.liquipedia
    needs_liquipedia = (
        liq_cfg.hltv_fallback
        or liq_cfg.upcoming_matches.enabled
        or liq_cfg.transfers.enabled
    )
    liquipedia_client = LiquipediaClient.from_config(liq_cfg) if needs_liquipedia else None

    return (
        [
            HLTVMatchesCollector(
                browser_client=hltv_browser_client,
                liquipedia_client=liquipedia_client if liq_cfg.hltv_fallback else None,
            ),
            HLTVNewsCollector(browser_client=hltv_browser_client),
            PodcastCollector(),
            RedditCollector(),
            SteamCollector(),
            YouTubeCollector(),
        ],
        hltv_browser_client,
        liquipedia_client,
    )


def build_collectors() -> list[BaseCollector]:
    collectors, _, _ = _build_collectors_with_shared_hltv_client()
    return collectors
```

Modify `run_collectors` to also close the Liquipedia client. Locate the current `try` / `finally` block in `run_collectors` and update it to:

```python
    collectors, hltv_browser_client, liquipedia_client = _build_collectors_with_shared_hltv_client()
    ...
    try:
        ...  # existing body unchanged
    finally:
        await hltv_browser_client.close()
        if liquipedia_client is not None:
            await liquipedia_client.close()
```

- [ ] **Step 3: Smoke-test the full pipeline against a known-broken HLTV match**

```powershell
.venv\Scripts\python.exe -m overpass
```

Expected: the run completes. Where previously you saw `Failed to collect HLTV match` for the `'-'` cases, you should now see either a successful match (rescued by Liquipedia) or, if Liquipedia also can't help, the same drop with both errors logged. The HTML briefing renders to `output/briefings/2026-04-23.html`.

If the `_build_collectors_with_shared_hltv_client` rename clashes with anything, search for callers:

```powershell
.venv\Scripts\Select-String -Path overpass\**\*.py,tests\**\*.py -Pattern "_build_collectors_with_shared_hltv_client"
```

Update any callers to unpack three values instead of two.

- [ ] **Step 4: Commit**

```powershell
git add overpass/main.py
git commit -m "feat(main): wire shared LiquipediaClient into HLTV collector"
```

---

## Self-review checklist (run after writing the plan, fix inline)

- [x] **Spec coverage:**
  - Module layout (cache/ratelimit/client/pages/matches/models) → Tasks 2-6
  - Soft-fail everywhere → checked in client (`_fetch_json`), pages, matches, fallback wiring
  - Config block with defaults → Task 1
  - User-Agent with contact interpolation → Task 1 + tested
  - On-disk cache with TTL + schema version → Task 2
  - Global rate limiter → Task 3
  - Page-finder with token-match filter → Task 5
  - Tournament-page parser with name normalization → Task 6
  - HLTV fallback wiring → Task 7
  - Pipeline wiring + cleanup → Task 8
  - Tests for every component → present
  - `.cache/` in `.gitignore` → Task 1 Step 6
  - Fixture-first parser development → Task 0

- [x] **Placeholders:** None. The only "REPLACE these" line in Task 6 is a deliberate concrete instruction tied to Task 0.

- [x] **Type consistency:** `LiquipediaClient.from_config(cfg, *, transport=None)` consistent across Tasks 4/8. `find_match_page(client, event_name)` consistent across Tasks 5/7. `parse_match_from_tournament_page(html, t1, t2)` consistent across Tasks 6/7. `LiquipediaMatch` / `LiquipediaMap` field names consistent across Tasks 6/7.

- [x] **Out-of-scope drift:** No briefing template changes anywhere. No new collectors. The dormant `upcoming_matches` and `transfers` config blocks exist but no collectors consume them in this plan — sub-features 2 and 3 will.

