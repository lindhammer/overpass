# Overpass – CS2 Daily Briefing & Live Alerts

## Overview

Overpass is a personal CS2 information aggregator that delivers a curated daily digest and real-time alerts via Telegram. It collects data from multiple sources, runs it through an LLM-powered editorial layer for contextual curation, and renders a structured briefing accessible through a clean mobile-first web UI.

The name references the iconic CS2 map while capturing the tool's purpose: a complete overview of everything that matters in CS2, every day.

---

## Core Features

### Daily Digest (Cron, ~07:00)

A Telegram push notification with a one-line LLM-generated summary, e.g.:

> "Parivision fumble against MongolZ in OT, ropz earns first MVP with Vitality, PGL Bucharest Playoffs live"

Tapping the notification opens the full briefing in a mobile-first web UI with a consistent layout and the following sections:

**Match Results**

- All results from the last 24h involving Top 30 teams + watchlist teams
- Scorelines, maps played, map pick/ban sequence
- Contextual highlights surfaced by LLM (e.g. "ZywOo posts career-low 0.68 rating on Mirage" or "Spirit extend win streak to 14 maps")
- Impact on HLTV rankings and tournament standings where relevant

**Top Clips**

- 3–5 highest-scoring clips from r/GlobalOffensive (Highlight/Clip flair)
- Thumbnail, title, score, link

**Top Tweets / Social**

- Notable pro player tweets: banter, roster hints, drama, reactions
- Curated by relevance, not volume

**Roster Moves & News**

- Transfers, benchings, stand-ins, org announcements
- Sources: HLTV, Liquipedia, Dust2

**Upcoming Matches**

- Today's and tomorrow's scheduled matches for watchlist teams + notable Top 30 matchups
- Times in local timezone, stream links

**Podcast & Content Drops**

- New episodes from tracked podcasts (HLTV Confirmed, etc.)
- New videos from tracked YouTube channels

**Patch Notes & Meta**

- Valve CS2 updates via Steam News API
- Summary of changes (LLM-generated)

**Tournament Tracker**

- Currently running events, upcoming events, qualifier stages
- Bracket status for active tournaments

**This Day in CS**

- A historic clip/moment from this calendar date
- Clip embed/link with short contextual description (LLM-written)

### Live Alerts (Event-Driven)

Real-time Telegram push notifications for configurable triggers:

- Watchlist team match goes live
- Valve patch drops
- Major roster move breaks
- Tournament stage transitions (e.g. "Playoffs begin")

Short, single-purpose notifications – not a full digest. The web UI includes a "Live" tab showing today's alerts chronologically.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   SCHEDULER                      │
│  Daily Digest: cron / systemd timer @ 07:00     │
│  Live Alerts:  persistent polling (5-10 min)     │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│              COLLECTOR LAYER                     │
│                                                 │
│  hltv_collector       → matches, news, rosters  │
│  reddit_collector     → clips, discussions      │
│  youtube_collector    → new videos              │
│  podcast_collector    → RSS feed polling         │
│  steam_collector      → patch notes             │
│  liquipedia_collector → events, brackets        │
│  twitter_collector    → pro player tweets (TBD) │
│  thisday_collector    → historical moments       │
│                                                 │
│  Each collector outputs standardized JSON        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│               DATA STORE (SQLite)                │
│                                                 │
│  - Historical player/team stats for context      │
│  - Deduplication (seen clips, sent alerts)       │
│  - Briefing archive                              │
│  - "This Day in CS" reference data               │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│          EDITORIAL LAYER (LLM)                   │
│                                                 │
│  Provider-agnostic interface:                    │
│  ├── Gemini (default, free tier)                │
│  └── Claude (better prose, paid)                │
│                                                 │
│  Tasks:                                          │
│  1. Curation     – What is newsworthy?           │
│  2. Context      – Why is it newsworthy?         │
│  3. Digest       – Structured briefing output    │
│  4. Summary Line – One-sentence Telegram push    │
│  5. This Day     – Historical moment description │
│  6. Patch Notes  – Human-readable changelog      │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│              DELIVERY LAYER                      │
│                                                 │
│  Telegram Bot                                    │
│  ├── Daily push with summary + link to web UI   │
│  └── Live alert notifications                    │
│                                                 │
│  Web UI                                          │
│  ├── Full briefing view (mobile-first, dark)     │
│  ├── Live tab (today's alerts)                   │
│  ├── Briefing archive (past digests)             │
│  └── Served from NUC via Tailscale              │
└─────────────────────────────────────────────────┘
```

---

## Data Sources

| Source     | API/Method                             | Cost                 | Reliability          | Data                           |
| ---------- | -------------------------------------- | -------------------- | -------------------- | ------------------------------ |
| HLTV       | Community scraper / `hltv-async-api`   | Free                 | Medium (anti-scrape) | Matches, stats, news, rosters  |
| Reddit     | Official API (OAuth, personal use)     | Free                 | High                 | Clips, highlights, discussions |
| YouTube    | Data API v3                            | Free (10k units/day) | High                 | Channel uploads, VODs          |
| Podcasts   | RSS feeds                              | Free                 | High                 | Episode drops                  |
| Steam      | `ISteamNews/GetNewsForApp` (appid 730) | Free                 | High                 | Patch notes, updates           |
| Liquipedia | MediaWiki API                          | Free                 | High                 | Events, brackets, rosters      |
| Twitter/X  | TBD (RSS bridges, unofficial scrapers) | Varies               | Low                  | Pro player tweets              |

### Twitter/X Strategy

Official API is prohibitively expensive. Viable alternatives to evaluate:

- RSSHub bridges for specific accounts
- Nitter instances (declining availability)
- Unofficial scrapers (legal gray area)
- Manual curation of a tweet list as fallback
- Skip entirely in MVP, add later

---

## Tech Stack

| Component       | Technology                            | Rationale                                            |
| --------------- | ------------------------------------- | ---------------------------------------------------- |
| Collectors      | Python                                | Consistent with existing projects (Socials Archiver) |
| Data Store      | SQLite                                | Local-first, no server dependency, familiar          |
| Editorial Layer | LLM via HTTP (Gemini / Claude)        | Provider-agnostic interface, swap anytime            |
| Telegram Bot    | `python-telegram-bot`                 | Mature library, async support                        |
| Web UI          | Jinja2 → static HTML (or React later) | Simple, no runtime server needed for display         |
| Scheduling      | systemd timers / cron                 | NUC-native, no extra dependencies                    |
| Live Polling    | Async Python process (asyncio)        | Long-running, efficient                              |
| Deployment      | Docker on NUC (server-lumen)          | Consistent with existing infra                       |
| Access          | Tailscale                             | Existing network, secure                             |

---

## Configuration

```yaml
# config.yaml

watchlist_teams:
  - Vitality
  - G2
  - FaZe
  - Spirit

hltv_top_n: 30

youtube_channels:
  - id: "UC_SgBkrOEFVnJkBMKcpp5lg"
    name: "HLTV"
  # add more

podcasts:
  - name: "HLTV Confirmed"
    feed_url: "https://..."
  - name: "Dust2 Podcast"
    feed_url: "https://..."

reddit:
  subreddit: "GlobalOffensive"
  sort: "top"
  time_filter: "day"
  limit: 10
  flair_filter:
    - "Highlight"
    - "Clip"

live_alerts:
  watchlist_match_live: true
  valve_patch: true
  roster_moves: true
  tournament_stage_change: true

llm:
  default_provider: "gemini"
  providers:
    gemini:
      model: "gemini-2.0-flash"
      api_key_env: "GEMINI_API_KEY"
    claude:
      model: "claude-sonnet-4-20250514"
      api_key_env: "ANTHROPIC_API_KEY"

telegram:
  bot_token_env: "TELEGRAM_BOT_TOKEN"
  chat_id_env: "TELEGRAM_CHAT_ID"

schedule:
  daily_digest: "07:00"
  live_poll_interval_minutes: 5

timezone: "Europe/Berlin"
```

---

## Web UI Design

- **Mobile-first**, dark theme (esports aesthetic)
- **Consistent layout** – every digest looks the same
- **Sections**: Summary → Matches → Clips → Social → Roster News → Upcoming → Podcasts/Content → Patches → Tournaments → This Day in CS
- **Collapsible sections** with "show more" for dense content
- **Live tab**: chronological alert feed for today
- **Archive**: browse past briefings by date
- **Static HTML**: generated once per digest, no backend needed for viewing

---

## MVP Scope (Phase 1)

**Goal**: End-to-end pipeline working with the easiest data sources, delivering a real daily digest.

### Collectors (MVP)

1. Podcasts (RSS – trivial)
2. Steam Patch Notes (official API)
3. Reddit Clips (official API)
4. YouTube Channel Uploads (official API)

### Editorial Layer (MVP)

- Gemini for digest structuring and summary line
- Simple prompt, no historical context yet

### Delivery (MVP)

- Telegram bot: daily push with summary + link
- Static HTML briefing served from NUC

### Not in MVP

- HLTV match results / stats (needs scraper evaluation)
- Twitter/X integration
- Live alerts
- This Day in CS (needs curated dataset)
- LLM contextual highlights (needs historical data)
- Briefing archive UI

---

## Phase 2

- HLTV collector (matches, news, rosters)
- Liquipedia collector (events, brackets)
- Match results section with basic stats
- Upcoming matches section
- Tournament tracker

## Phase 3

- Live alerts (persistent polling + Telegram notifications)
- Historical stats in SQLite for LLM context
- Contextual highlights ("career-low rating", "win streak")
- This Day in CS (curated dataset + LLM descriptions)

## Phase 4

- Twitter/X integration (evaluate available methods)
- Claude as alternative LLM provider
- Briefing archive with browse UI
- Article generation from digest data (stretch goal)

---

## Repository

- **Name**: `overpass`
- **GitHub**: `lindhammer/overpass`
- **Language**: Python
- **License**: Private

---

## Open Questions

1. **This Day in CS data source** – Is there a community-maintained database of historic CS moments by date, or does this need to be manually curated / scraped from HLTV/Liquipedia?
2. **HLTV scraper reliability** – Which community API/scraper is currently most stable? Needs evaluation before Phase 2.
3. **Telegram bot UX** – Should the bot support commands (e.g. `/digest`, `/live`, `/upcoming`) or is push-only sufficient?
4. **Web UI framework** – Start with Jinja2 static HTML, or go straight to React for interactivity (collapsible sections, live tab)?

