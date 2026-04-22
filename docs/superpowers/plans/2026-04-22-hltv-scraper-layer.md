# HLTV Scraper Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable Playwright-backed HLTV scraping layer that powers full-article news collection and detailed recent match collection for the daily digest, while remaining reusable for later live polling and alerts.

**Architecture:** Introduce a small HLTV package that separates browser fetching from HTML parsing and collector normalization. Keep the existing collector pipeline intact by adding two thin collectors, `HLTVNewsCollector` and `HLTVMatchesCollector`, that convert parsed HLTV entities into `CollectorItem` instances.

**Tech Stack:** Python 3.12, Playwright (Chromium), BeautifulSoup4, Pydantic, asyncio, pytest, pytest-asyncio.

---

## File Structure

**Create:**

- `overpass/hltv/__init__.py` – package marker and public exports
- `overpass/hltv/browser.py` – shared Playwright session, fetch, retry, and rate-limit helpers
- `overpass/hltv/models.py` – structured HLTV entity models used by parsers and collectors
- `overpass/hltv/news.py` – news listing and article-page parsers
- `overpass/hltv/matches.py` – results listing and match-detail parsers
- `overpass/collectors/hltv_news.py` – daily news collector using the HLTV scraper layer
- `overpass/collectors/hltv_matches.py` – recent detailed match collector using the HLTV scraper layer
- `tests/test_hltv_news_parser.py` – parser coverage for listing and article extraction
- `tests/test_hltv_news_collector.py` – collector normalization and time-window filtering tests
- `tests/test_hltv_matches_parser.py` – parser coverage for results, veto, map, and player-stat extraction
- `tests/test_hltv_matches_collector.py` – collector normalization, team filtering, and partial-failure tests
- `tests/fixtures/hltv_news_listing.html` – frozen HLTV news listing sample
- `tests/fixtures/hltv_news_article.html` – frozen HLTV article page sample
- `tests/fixtures/hltv_results.html` – frozen HLTV results page sample
- `tests/fixtures/hltv_match_detail.html` – frozen HLTV match page sample

**Modify:**

- `pyproject.toml` – add Playwright to runtime dependencies and optional dev helpers if needed
- `overpass/config.py` – add HLTV config and validation
- `config.yaml` – add HLTV section with limits and browser options
- `overpass/main.py` – register the two HLTV collectors in the Phase 2 pipeline
- `overpass/editorial/digest.py` – expose `News` and `Matches` section names
- `overpass/delivery/html.py` – update section order for new digest sections
- `overpass/templates/briefing.html` – render article excerpts and match metadata clearly
- `tests/test_html_delivery.py` – verify News and Matches render correctly when present

## Task 1: Add HLTV Configuration And Dependency Setup

**Files:**

- Modify: `pyproject.toml`
- Modify: `overpass/config.py`
- Modify: `config.yaml`
- Test: `python -m pytest tests/test_html_delivery.py -q`

- [ ] **Step 1: Add Playwright to project dependencies**

Update `pyproject.toml` so runtime dependencies include Playwright and BeautifulSoup4.

```toml
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "feedparser>=6.0",
    "python-dotenv>=1.0",
    "tzdata>=2024.1",
    "jinja2>=3.1",
    "python-telegram-bot>=20.0",
    "beautifulsoup4>=4.12",
    "playwright>=1.52",
]
```

- [ ] **Step 2: Add an `HLTVConfig` model to the application config**

Extend `overpass/config.py` with a dedicated config model and attach it to `AppConfig`.

```python
class HLTVConfig(BaseModel):
    base_url: str = "https://www.hltv.org"
    headless: bool = True
    news_limit: int = 20
    results_pages: int = 1
    request_timeout_seconds: int = 30
    min_request_interval_seconds: float = 2.0
    watchlist_only_matches: bool = False


class AppConfig(BaseModel):
    watchlist_teams: list[str] = []
    hltv_top_n: int = 30
    hltv: HLTVConfig = HLTVConfig()
    youtube: YouTubeConfig = YouTubeConfig()
    podcasts: list[Podcast] = []
    reddit: RedditConfig = RedditConfig(subreddit="GlobalOffensive")
```

- [ ] **Step 3: Add HLTV defaults to `config.yaml`**

Add a new top-level `hltv:` section.

```yaml
hltv:
  base_url: "https://www.hltv.org"
  headless: true
  news_limit: 20
  results_pages: 1
  request_timeout_seconds: 30
  min_request_interval_seconds: 2.0
  watchlist_only_matches: false
```

- [ ] **Step 4: Install dependencies and browser locally**

Run:

```bash
pip install -e .
python -m playwright install chromium
```

Expected: `playwright` installs successfully and Chromium download completes.

- [ ] **Step 5: Run a quick regression test**

Run:

```bash
pytest tests/test_html_delivery.py -q
```

Expected: PASS. Existing Phase 1 delivery behavior should remain intact after config changes.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml overpass/config.py config.yaml
git commit -m "chore: add hltv configuration and playwright dependency"
```

## Task 2: Build The Shared HLTV Browser Client

**Files:**

- Create: `overpass/hltv/__init__.py`
- Create: `overpass/hltv/browser.py`
- Modify: `overpass/config.py`
- Test: `tests/test_hltv_news_collector.py`

- [ ] **Step 1: Write a failing browser-client smoke test**

Create a unit test that patches Playwright and verifies one fetch call returns rendered HTML and respects a minimum interval between requests.

```python
@pytest.mark.asyncio
async def test_fetch_html_returns_page_content_and_closes_resources():
    client = HLTVBrowserClient(base_url="https://www.hltv.org", headless=True, timeout_seconds=30, min_interval_seconds=0)
    html = await client.fetch_html("/news")
    assert "<html" in html.lower()
```

- [ ] **Step 2: Implement the shared browser client**

Create `overpass/hltv/browser.py` with a small async client that owns startup, shutdown, retries, and page content extraction.

```python
class HLTVBrowserClient:
    def __init__(self, base_url: str, headless: bool, timeout_seconds: int, min_interval_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self._playwright = None
        self._browser = None
        self._context = None
        self._last_request_at = 0.0

    async def fetch_html(self, path_or_url: str) -> str:
        url = self._to_url(path_or_url)
        await self._ensure_started()
        await self._respect_rate_limit()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
            await page.wait_for_load_state("networkidle", timeout=self.timeout_seconds * 1000)
            return await page.content()
        finally:
            await page.close()
```

- [ ] **Step 3: Expose a clean package API**

Create `overpass/hltv/__init__.py`.

```python
from overpass.hltv.browser import HLTVBrowserClient

__all__ = ["HLTVBrowserClient"]
```

- [ ] **Step 4: Run the new browser-client test**

Run:

```bash
pytest tests/test_hltv_news_collector.py -q
```

Expected: PASS for the patched smoke test without launching a real browser in CI.

- [ ] **Step 5: Commit**

```bash
git add overpass/hltv/__init__.py overpass/hltv/browser.py tests/test_hltv_news_collector.py
git commit -m "feat: add shared hltv browser client"
```

## Task 3: Add HLTV News Models And Parsers

**Files:**

- Create: `overpass/hltv/models.py`
- Create: `overpass/hltv/news.py`
- Create: `tests/test_hltv_news_parser.py`
- Create: `tests/fixtures/hltv_news_listing.html`
- Create: `tests/fixtures/hltv_news_article.html`

- [ ] **Step 1: Write failing parser tests for listing and article pages**

Create tests that load frozen HTML fixtures and assert the parser extracts article metadata and cleaned body text.

```python
def test_parse_news_listing_extracts_article_links_and_timestamps():
    html = Path("tests/fixtures/hltv_news_listing.html").read_text()
    articles = parse_news_listing(html, base_url="https://www.hltv.org")
    assert articles[0].title
    assert articles[0].url.startswith("https://www.hltv.org/news/")


def test_parse_article_page_extracts_full_body_text():
    html = Path("tests/fixtures/hltv_news_article.html").read_text()
    article = parse_article_page(html, url="https://www.hltv.org/news/123/example")
    assert len(article.body_text) > 200
    assert "\n\n" in article.body_text
```

- [ ] **Step 2: Define structured models for HLTV entities**

Create `overpass/hltv/models.py`.

```python
class HLTVNewsArticle(BaseModel):
    external_id: str
    title: str
    url: str
    published_at: datetime
    teaser: str = ""
    body_text: str = ""
    author: str | None = None
    thumbnail_url: str | None = None
    tags: list[str] = []


class HLTVMatch(BaseModel):
    external_id: str
    url: str
    start_time: datetime
    event_name: str
    team1: str
    team2: str
    status: str
    score: str = ""
    maps: list[dict[str, str | int]] = []
    veto: list[str] = []
    player_stats: list[dict[str, str | float]] = []
```

- [ ] **Step 3: Implement the news listing and article parsers**

Create `overpass/hltv/news.py` as pure parsing helpers.

```python
def parse_news_listing(html: str, base_url: str) -> list[HLTVNewsArticle]:
    soup = BeautifulSoup(html, "html.parser")
    articles: list[HLTVNewsArticle] = []
    for card in soup.select("a.article"):
        title = card.select_one(".newstext").get_text(" ", strip=True)
        href = card.get("href", "")
        url = urljoin(base_url, href)
        published_at = _parse_news_timestamp(card)
        articles.append(
            HLTVNewsArticle(
                external_id=_extract_news_id(url),
                title=title,
                url=url,
                published_at=published_at,
                teaser=_extract_teaser(card),
                thumbnail_url=_extract_listing_image(card),
            )
        )
    return articles


def parse_article_page(html: str, url: str) -> HLTVNewsArticle:
    soup = BeautifulSoup(html, "html.parser")
    body = "\n\n".join(p.get_text(" ", strip=True) for p in soup.select(".news-body p") if p.get_text(strip=True))
    return HLTVNewsArticle(
        external_id=_extract_news_id(url),
        title=soup.select_one(".article h1").get_text(" ", strip=True),
        url=url,
        published_at=_parse_article_timestamp(soup),
        teaser=_extract_article_teaser(soup),
        body_text=body,
        author=_extract_author(soup),
        thumbnail_url=_extract_article_image(soup),
        tags=_extract_tags(soup),
    )
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
pytest tests/test_hltv_news_parser.py -q
```

Expected: PASS. The parser should extract stable fields from frozen HTML without network access.

- [ ] **Step 5: Commit**

```bash
git add overpass/hltv/models.py overpass/hltv/news.py tests/test_hltv_news_parser.py tests/fixtures/hltv_news_listing.html tests/fixtures/hltv_news_article.html
git commit -m "feat: add hltv news parsers"
```

## Task 4: Add The HLTV News Collector

**Files:**

- Create: `overpass/collectors/hltv_news.py`
- Create: `tests/test_hltv_news_collector.py`
- Modify: `overpass/main.py`
- Modify: `overpass/editorial/digest.py`

- [ ] **Step 1: Write a failing collector test for 24-hour filtering and normalization**

```python
@pytest.mark.asyncio
async def test_collect_returns_recent_articles_with_full_text_metadata():
    collector = HLTVNewsCollector(browser_client=FakeBrowserClient())
    items = await collector.collect()
    assert len(items) == 1
    assert items[0].type == "article"
    assert items[0].metadata["body_text"].startswith("Roster")
```

- [ ] **Step 2: Implement `HLTVNewsCollector` as a thin orchestrator**

```python
class HLTVNewsCollector(BaseCollector):
    name = "hltv_news"

    def __init__(self, browser_client: HLTVBrowserClient | None = None) -> None:
        super().__init__()
        self._browser_client = browser_client

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        browser = self._browser_client or HLTVBrowserClient(
            base_url=config.hltv.base_url,
            headless=config.hltv.headless,
            timeout_seconds=config.hltv.request_timeout_seconds,
            min_interval_seconds=config.hltv.min_request_interval_seconds,
        )
        listing_html = await browser.fetch_html("/news/archive")
        listing_articles = parse_news_listing(listing_html, config.hltv.base_url)
        recent_articles = [article for article in listing_articles if article.published_at >= _cutoff_24h()][: config.hltv.news_limit]
        return [await self._build_item(browser, article) for article in recent_articles]
```

- [ ] **Step 3: Register the collector and editorial section name**

Update `overpass/main.py` and `overpass/editorial/digest.py`.

```python
COLLECTORS: list[BaseCollector] = [
    PodcastCollector(),
    RedditCollector(),
    SteamCollector(),
    YouTubeCollector(),
    HLTVNewsCollector(),
]
```

```python
_SECTION_NAMES: dict[str, str] = {
    "article": "News",
    "clip": "Clips",
    "episode": "Podcasts",
    "patch": "Patches",
    "video": "Videos",
}
```

- [ ] **Step 4: Run the collector tests**

Run:

```bash
pytest tests/test_hltv_news_collector.py -q
```

Expected: PASS. Old articles should be skipped, article fetch failures should skip only the broken article, and normalized `CollectorItem` metadata should include full article text.

- [ ] **Step 5: Commit**

```bash
git add overpass/collectors/hltv_news.py overpass/main.py overpass/editorial/digest.py tests/test_hltv_news_collector.py
git commit -m "feat: add hltv news collector"
```

## Task 5: Add HLTV Match Parsers For Results, Veto, And Stats

**Files:**

- Create: `overpass/hltv/matches.py`
- Create: `tests/test_hltv_matches_parser.py`
- Create: `tests/fixtures/hltv_results.html`
- Create: `tests/fixtures/hltv_match_detail.html`
- Modify: `overpass/hltv/models.py`

- [ ] **Step 1: Write failing parser tests for results pages and detailed match pages**

```python
def test_parse_results_listing_extracts_match_links():
    html = Path("tests/fixtures/hltv_results.html").read_text()
    matches = parse_results_listing(html, base_url="https://www.hltv.org")
    assert matches[0].team1 == "Vitality"
    assert matches[0].url.startswith("https://www.hltv.org/matches/")


def test_parse_match_page_extracts_maps_veto_and_player_stats():
    html = Path("tests/fixtures/hltv_match_detail.html").read_text()
    match = parse_match_page(html, url="https://www.hltv.org/matches/123/example")
    assert match.veto
    assert match.maps
    assert match.player_stats
```

- [ ] **Step 2: Implement results-page parsing**

```python
def parse_results_listing(html: str, base_url: str) -> list[HLTVMatch]:
    soup = BeautifulSoup(html, "html.parser")
    matches: list[HLTVMatch] = []
    for card in soup.select(".result-con"):
        url = urljoin(base_url, card.get("href", ""))
        matches.append(
            HLTVMatch(
                external_id=_extract_match_id(url),
                url=url,
                start_time=_parse_match_time(card),
                event_name=_extract_event_name(card),
                team1=_extract_team_name(card, 1),
                team2=_extract_team_name(card, 2),
                status="finished",
                score=_extract_score(card),
            )
        )
    return matches
```

- [ ] **Step 3: Implement match-detail parsing**

```python
def parse_match_page(html: str, url: str) -> HLTVMatch:
    soup = BeautifulSoup(html, "html.parser")
    match = _parse_match_header(soup, url)
    match.maps = _extract_maps(soup)
    match.veto = _extract_veto(soup)
    match.player_stats = _extract_player_stats(soup)
    return match
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
pytest tests/test_hltv_matches_parser.py -q
```

Expected: PASS. Frozen fixtures should prove the parser can recover the recent result, map scores, veto sequence, and at least one stat row per team.

- [ ] **Step 5: Commit**

```bash
git add overpass/hltv/matches.py overpass/hltv/models.py tests/test_hltv_matches_parser.py tests/fixtures/hltv_results.html tests/fixtures/hltv_match_detail.html
git commit -m "feat: add hltv match parsers"
```

## Task 6: Add The HLTV Matches Collector

**Files:**

- Create: `overpass/collectors/hltv_matches.py`
- Create: `tests/test_hltv_matches_collector.py`
- Modify: `overpass/main.py`
- Modify: `overpass/editorial/digest.py`

- [ ] **Step 1: Write a failing collector test for match filtering and normalization**

```python
@pytest.mark.asyncio
async def test_collect_returns_recent_watchlist_or_top_matches_with_detail():
    collector = HLTVMatchesCollector(browser_client=FakeBrowserClient())
    items = await collector.collect()
    assert items[0].type == "match"
    assert items[0].metadata["maps"]
    assert items[0].metadata["veto"]
```

- [ ] **Step 2: Implement `HLTVMatchesCollector`**

```python
class HLTVMatchesCollector(BaseCollector):
    name = "hltv_matches"

    async def collect(self) -> list[CollectorItem]:
        config = load_config()
        browser = self._make_browser(config)
        listing_html = await browser.fetch_html("/results")
        recent = parse_results_listing(listing_html, config.hltv.base_url)
        filtered = [match for match in recent if _is_recent(match.start_time) and _is_relevant_match(match, config.watchlist_teams)]
        detailed_matches = [await self._hydrate_match(browser, match) for match in filtered]
        return [self._to_item(match) for match in detailed_matches]
```

- [ ] **Step 3: Register the matches collector and section name**

```python
COLLECTORS: list[BaseCollector] = [
    PodcastCollector(),
    RedditCollector(),
    SteamCollector(),
    YouTubeCollector(),
    HLTVNewsCollector(),
    HLTVMatchesCollector(),
]
```

```python
_SECTION_NAMES: dict[str, str] = {
    "article": "News",
    "match": "Matches",
    "clip": "Clips",
    "episode": "Podcasts",
    "patch": "Patches",
    "video": "Videos",
}
```

- [ ] **Step 4: Run the collector tests**

Run:

```bash
pytest tests/test_hltv_matches_collector.py -q
```

Expected: PASS. The collector should keep only recent relevant matches, skip malformed detail pages individually, and include maps, veto, and player stats in metadata.

- [ ] **Step 5: Commit**

```bash
git add overpass/collectors/hltv_matches.py overpass/main.py overpass/editorial/digest.py tests/test_hltv_matches_collector.py
git commit -m "feat: add hltv matches collector"
```

## Task 7: Render News And Matches In The Briefing UI

**Files:**

- Modify: `overpass/delivery/html.py`
- Modify: `overpass/templates/briefing.html`
- Modify: `tests/test_html_delivery.py`

- [ ] **Step 1: Write failing HTML tests for News and Matches sections**

Add representative fixtures to `tests/test_html_delivery.py` and assert the new sections render article excerpts, scorelines, maps, and veto content.

```python
def test_news_body_excerpt_appears_in_html():
    digest = _digest_with_news_and_matches()
    html = render_briefing(digest, _DATE)
    assert "Falcons confirmed" in html


def test_match_score_maps_and_veto_appear_in_html():
    digest = _digest_with_news_and_matches()
    html = render_briefing(digest, _DATE)
    assert "Vitality vs Spirit" in html
    assert "Mirage 13-9" in html
    assert "Vitality removed Anubis" in html
```

- [ ] **Step 2: Update section ordering in `overpass/delivery/html.py`**

```python
SECTION_ORDER = ["Matches", "News", "Clips", "Videos", "Podcasts", "Patches"]
```

- [ ] **Step 3: Extend the template for article and match metadata**

Add article excerpt rendering from `metadata.body_text` / `metadata.teaser`, and match metadata rendering from `metadata.score`, `metadata.maps`, `metadata.veto`, and `metadata.event`.

```jinja2
{% elif item.type == "article" %}
  <div class="card-excerpt">{{ item.metadata.body_text or item.metadata.teaser }}</div>
{% elif item.type == "match" %}
  <div class="card-meta">
    <span>{{ item.metadata.event }}</span>
    <span>{{ item.metadata.score }}</span>
  </div>
  <div class="card-excerpt">{{ item.metadata.maps | join(", ") }}</div>
{% endif %}
```

- [ ] **Step 4: Run the HTML tests**

Run:

```bash
pytest tests/test_html_delivery.py -q
```

Expected: PASS. Existing sections still render, and the new News and Matches sections display the key extracted HLTV data.

- [ ] **Step 5: Commit**

```bash
git add overpass/delivery/html.py overpass/templates/briefing.html tests/test_html_delivery.py
git commit -m "feat: render hltv news and matches in briefing"
```

## Task 8: Run End-To-End Validation And Document Operating Notes

**Files:**

- Modify: `README.md`
- Test: `tests/test_hltv_news_parser.py`
- Test: `tests/test_hltv_news_collector.py`
- Test: `tests/test_hltv_matches_parser.py`
- Test: `tests/test_hltv_matches_collector.py`
- Test: `tests/test_html_delivery.py`

- [ ] **Step 1: Add a short HLTV setup note to the README**

Document that Chromium must be installed locally for HLTV scraping.

````md
## HLTV scraping setup

HLTV scraping uses Playwright with Chromium.

```bash
pip install -e .
python -m playwright install chromium
```
````

```

```

- [ ] **Step 2: Run the focused HLTV and delivery test suite**

Run:

```bash
pytest tests/test_hltv_news_parser.py tests/test_hltv_news_collector.py tests/test_hltv_matches_parser.py tests/test_hltv_matches_collector.py tests/test_html_delivery.py -q
```

Expected: PASS. News and matches parse from fixtures, collectors normalize correctly, and briefing rendering covers the new sections.

- [ ] **Step 3: Run the full project test suite**

Run:

```bash
pytest -q
```

Expected: PASS. HLTV support should not regress the existing Reddit, podcast, Steam, YouTube, editorial, or delivery behavior.

- [ ] **Step 4: Smoke-test the full pipeline manually**

Run:

```bash
overpass
```

Expected: the run completes, logs HLTV collection counts, writes the daily briefing HTML, and sends or skips Telegram notification depending on local credentials.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add hltv scraping setup notes"
```

## Self-Review

- **Spec coverage:** This plan covers the approved scope: full HLTV article scraping, recent top/relevant matches, Playwright-backed fetching, thin collectors that fit the existing pipeline, and a scraper surface reusable for future frequent polling. It intentionally does not include SQLite dedupe, live alert state transitions, or upcoming matches; those remain later tasks once the scraper contract is stable.
- **Placeholder scan:** The plan avoids `TBD`, `TODO`, and vague “handle edge cases” instructions. Each task names exact files, includes concrete commands, and shows representative code for the main contract being introduced.
- **Type consistency:** The plan uses `HLTVNewsCollector`, `HLTVMatchesCollector`, `HLTVBrowserClient`, `HLTVNewsArticle`, and `HLTVMatch` consistently across config, parser, collector, and rendering tasks.

```

```

