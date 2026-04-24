# Reddit Public JSON Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Reddit OAuth from the collector and switch Overpass to the public subreddit `.json` listing without changing the emitted `CollectorItem` shape.

**Architecture:** Keep the existing Reddit parsing path and `CollectorItem` contract, but simplify transport: `RedditCollector.collect()` fetches directly from `https://www.reddit.com/r/{subreddit}/{sort}.json` with `limit`, `t`, and `User-Agent`. Configuration shrinks by removing Reddit credential fields, and the Reddit test suite is rewritten around the new no-auth contract.

**Tech Stack:** Python 3.12, httpx, pydantic v2, pytest, unittest.mock, YAML, dotenv.

**Spec:** [docs/superpowers/specs/2026-04-24-reddit-json-design.md](../specs/2026-04-24-reddit-json-design.md)

---

## File Map

- `overpass/config.py`: remove credential fields from `RedditConfig`.
- `config.yaml`: remove Reddit credential keys from the `reddit:` block.
- `.env`: remove unused Reddit credential variables.
- `overpass/collectors/reddit.py`: remove OAuth/token handling and fetch public listing JSON directly.
- `tests/test_config.py`: add config regression coverage for the smaller `RedditConfig` surface.
- `tests/test_reddit_collector.py`: replace OAuth-specific tests with public-listing transport and no-credentials behavior tests.
- `SPEC.md`: update architecture text that still claims Reddit uses the official OAuth API.

## Task 1: Shrink the Reddit config surface

**Files:**

- Modify: `tests/test_config.py`
- Modify: `overpass/config.py`
- Modify: `config.yaml`
- Modify: `.env`

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_reddit_config_has_no_credential_fields():
    from overpass.config import RedditConfig

    cfg = RedditConfig(subreddit="GlobalOffensive")

    assert not hasattr(cfg, "client_id_env")
    assert not hasattr(cfg, "client_secret_env")


def test_load_config_reads_reddit_block_without_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            'reddit:\n'
            '  subreddit: "GlobalOffensive"\n'
            '  sort: "hot"\n'
            '  time_filter: "day"\n'
            '  limit: 25\n'
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path)

    assert cfg.reddit.subreddit == "GlobalOffensive"
    assert cfg.reddit.sort == "hot"
    assert cfg.reddit.time_filter == "day"
    assert cfg.reddit.limit == 25
```

- [ ] **Step 2: Run the targeted config tests and verify the failure is real**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -k reddit -q
```

Expected: `test_reddit_config_has_no_credential_fields` fails because `RedditConfig` still exposes `client_id_env` and `client_secret_env`.

- [ ] **Step 3: Remove the credential fields from `RedditConfig`**

Edit `overpass/config.py` so `RedditConfig` becomes:

```python
class RedditConfig(BaseModel):
    subreddit: str
    sort: str = "top"
    time_filter: str = "day"
    limit: int = 10
    flair_filter: list[str] = []
    user_agent: str = "overpass:v0.1.0 (by /u/overpass-bot)"
```

Do not add replacement fields.

- [ ] **Step 4: Re-run the targeted config tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -k reddit -q
```

Expected: both Reddit-specific tests pass.

- [ ] **Step 5: Remove the dead credential entries from checked-in config files**

Edit `config.yaml` so the Reddit block becomes:

```yaml
reddit:
  subreddit: "GlobalOffensive"
  sort: "top"
  time_filter: "day"
  limit: 10
  flair_filter:
    - "Highlight"
    - "Clip"
  user_agent: "overpass:v0.1.0 (by /u/overpass-bot)"
```

Edit `.env` to remove these two lines entirely:

```text
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

- [ ] **Step 6: Smoke-test config loading from the real repo config**

Run:

```powershell
.venv\Scripts\python.exe -c "from overpass.config import load_config; cfg = load_config(); print(cfg.reddit.sort); print(hasattr(cfg.reddit, 'client_id_env')); print(hasattr(cfg.reddit, 'client_secret_env'))"
```

Expected:

- first line prints `top`
- second line prints `False`
- third line prints `False`

- [ ] **Step 7: Commit**

```powershell
git add tests/test_config.py overpass/config.py config.yaml .env
git commit -m "refactor(reddit): remove credential config"
```

---

## Task 2: Replace OAuth transport with direct public JSON fetches

**Files:**

- Modify: `tests/test_reddit_collector.py`
- Modify: `overpass/collectors/reddit.py`

- [ ] **Step 1: Write the failing transport and no-credentials tests**

In `tests/test_reddit_collector.py`, add these tests near the top of the file after the helpers:

```python
@pytest.mark.asyncio
async def test_fetch_posts_uses_public_json_listing():
    response = AsyncMock()
    response.raise_for_status.return_value = None
    response.json.return_value = SAMPLE_LISTING

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get.return_value = response

    with patch("overpass.collectors.reddit.httpx.AsyncClient", return_value=client):
        posts = await RedditCollector()._fetch_posts(_REDDIT_CFG)

    client.get.assert_awaited_once_with(
        "https://www.reddit.com/r/GlobalOffensive/top.json",
        params={"t": "day", "limit": 10},
        headers={"User-Agent": "overpass:v0.1.0 (by /u/test)"},
    )
    assert posts == [c["data"] for c in SAMPLE_LISTING["data"]["children"]]


@pytest.mark.asyncio
async def test_collect_without_credentials_still_fetches_posts():
    cfg = AppConfig(
        reddit=RedditConfig(
            subreddit="GlobalOffensive",
            sort="top",
            time_filter="day",
            limit=10,
            flair_filter=["Highlight", "Clip"],
            user_agent="overpass:v0.1.0 (by /u/test)",
        ),
        telegram={"bot_token_env": "", "chat_id_env": ""},
    )

    with (
        patch("overpass.collectors.reddit.load_config", return_value=cfg),
        _mock_fetch(),
    ):
        items = await RedditCollector().collect()

    assert [item.title for item in items] == [
        "insane 1v5 clutch by s1mple",
        "sick AWP ace on Inferno",
    ]
```

- [ ] **Step 2: Run just the new tests and verify the current implementation fails for the right reasons**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_reddit_collector.py -k "public_json_listing or without_credentials_still_fetches_posts" -q
```

Expected:

- `_fetch_posts()` fails because it still expects a token and calls the OAuth URL
- `collect()` fails because it still reads credential fields or tries to authenticate

- [ ] **Step 3: Rewrite `RedditCollector` to use the public listing endpoint only**

Edit `overpass/collectors/reddit.py` with these exact structural changes:

```python
"""Reddit collector - fetches top clips from r/GlobalOffensive via public JSON."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config

REDDIT_BASE = "https://www.reddit.com"


class RedditCollector(BaseCollector):
    name = "reddit"

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        reddit_cfg = config.reddit

        try:
            posts = await self._fetch_posts(reddit_cfg)
        except Exception:
            self.logger.exception("Failed to fetch Reddit posts")
            return []

        items: list[CollectorItem] = []
        for post in posts:
            try:
                item = self._parse_post(post, reddit_cfg.flair_filter)
                if item is not None:
                    items.append(item)
            except Exception:
                self.logger.exception("Failed to parse Reddit post")

        self.logger.info("Collected %d reddit clips", len(items))
        return items

    async def _fetch_posts(self, reddit_cfg) -> list[dict]:
        url = f"{REDDIT_BASE}/r/{reddit_cfg.subreddit}/{reddit_cfg.sort}.json"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                params={
                    "t": reddit_cfg.time_filter,
                    "limit": reddit_cfg.limit,
                },
                headers={
                    "User-Agent": reddit_cfg.user_agent,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        children = data.get("data", {}).get("children", [])
        return [child.get("data", {}) for child in children]
```

Delete all OAuth-specific code:

- `import time`
- `TOKEN_URL`
- `OAUTH_BASE`
- `__init__`
- `_get_access_token(...)`
- any `Authorization` header construction

- [ ] **Step 4: Re-run the targeted tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_reddit_collector.py -k "public_json_listing or without_credentials_still_fetches_posts" -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_reddit_collector.py overpass/collectors/reddit.py
git commit -m "refactor(reddit): fetch public subreddit json"
```

---

## Task 3: Rewrite the Reddit test suite and update stale documentation

**Files:**

- Modify: `tests/test_reddit_collector.py`
- Modify: `SPEC.md`

- [ ] **Step 1: Run the full Reddit test file and capture the stale-OAuth failures**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_reddit_collector.py -q
```

Expected: failures remain in the OAuth-only tests and helpers, even though the collector now uses public JSON.

- [ ] **Step 2: Remove OAuth-only helpers and replace the stale tests with public-contract coverage**

In `tests/test_reddit_collector.py`:

1. Delete `TOKEN_RESPONSE`.
2. Delete `_mock_auth(...)`.
3. Delete the entire `# ── Tests: OAuth2 authentication ─────────────────────────────────` section.
4. Update `_REDDIT_CFG` so it no longer passes credential fields:

```python
_REDDIT_CFG = RedditConfig(
    subreddit="GlobalOffensive",
    sort="top",
    time_filter="day",
    limit=10,
    flair_filter=["Highlight", "Clip"],
    user_agent="overpass:v0.1.0 (by /u/test)",
)
```

5. Update every remaining `with _mock_config(), _mock_auth(), _mock_fetch():` block to:

```python
with _mock_config(), _mock_fetch():
    items = await RedditCollector().collect()
```

6. Keep the public tests from Task 2 plus the existing behavior tests for:

- flair filtering
- item fields
- reddit_video fallback URL extraction
- self thumbnail suppression
- empty listing
- fetch failure
- malformed post skip

- [ ] **Step 3: Re-run the full Reddit test file and verify it is green**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_reddit_collector.py -q
```

Expected: the entire file passes with no OAuth references.

- [ ] **Step 4: Update `SPEC.md` so it matches the new runtime contract**

Make these two exact text changes in `SPEC.md`:

```markdown
| Reddit | Public subreddit `.json` listing | Free | Medium | Clips, highlights, discussions |
```

and

```markdown
3. Reddit Clips (public `.json` listing)
```

- [ ] **Step 5: Verify the cleaned-up files no longer mention removed Reddit credentials or OAuth**

Run:

```powershell
rg "REDDIT_CLIENT_ID|REDDIT_CLIENT_SECRET|OAuth2|Official API \(OAuth" overpass/config.py config.yaml .env overpass/collectors/reddit.py tests/test_reddit_collector.py SPEC.md
```

Expected: no output.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_reddit_collector.py SPEC.md
git commit -m "test(docs): align reddit suite and spec with public json"
```

---

## Final Verification

- [ ] **Step 1: Run the touched test slices together**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_reddit_collector.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Optional smoke check against the live public endpoint**

Run:

```powershell
.venv\Scripts\python.exe -c "import asyncio; from overpass.collectors.reddit import RedditCollector; items = asyncio.run(RedditCollector().collect()); print(len(items)); print(items[0].title if items else 'no-items')"
```

Expected: prints a non-negative integer and either the first clip title or `no-items`. This is a smoke check only; do not fail the branch on transient Reddit/network issues.

