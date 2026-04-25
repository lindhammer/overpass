"""Daily briefing pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.collectors.hltv_matches import HLTVMatchesCollector
from overpass.collectors.hltv_news import HLTVNewsCollector
from overpass.collectors.hltv_upcoming import HLTVUpcomingCollector
from overpass.collectors.podcast import PodcastCollector
from overpass.collectors.reddit import RedditCollector
from overpass.collectors.social import NitterSocialCollector
from overpass.collectors.steam import SteamCollector
from overpass.collectors.youtube import YouTubeCollector
from overpass.config import load_config
from overpass.delivery.html import briefing_path_for_date, render_briefing, save_briefing
from overpass.delivery.telegram import send_digest_notification
from overpass.editorial.digest import generate_digest
from overpass.editorial.gemini import GeminiProvider
from overpass.history.lookup import get_primary_for
from overpass.hltv.browser import HLTVBrowserClient
from overpass.liquipedia.client import LiquipediaClient

logger = logging.getLogger("overpass")


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
            HLTVUpcomingCollector(browser_client=hltv_browser_client),
            PodcastCollector(),
            RedditCollector(),
            NitterSocialCollector(),
            SteamCollector(),
            YouTubeCollector(),
        ],
        hltv_browser_client,
        liquipedia_client,
    )


def build_collectors() -> list[BaseCollector]:
    collectors, _, _ = _build_collectors_with_shared_hltv_client()
    return collectors


async def run_collectors() -> list[CollectorItem]:
    """Run every registered collector concurrently; log per-collector counts."""
    config = load_config()
    collectors, hltv_browser_client, liquipedia_client = _build_collectors_with_shared_hltv_client()
    logger.info("Timezone: %s", config.tz)
    logger.info("Running %d collectors", len(collectors))

    t0 = time.monotonic()
    try:
        results = await asyncio.gather(
            *(collector.collect() for collector in collectors),
            return_exceptions=True,
        )
        logger.info("Collectors finished in %.1fs", time.monotonic() - t0)

        items: list[CollectorItem] = []
        for collector, result in zip(collectors, results):
            if isinstance(result, BaseException):
                logger.error("Collector %s failed: %s", collector.name, result)
            else:
                logger.info("  %-10s -> %d items", collector.name, len(result))
                items.extend(result)

        logger.info("Total items collected: %d", len(items))
        return items
    finally:
        await hltv_browser_client.close()
        if liquipedia_client is not None:
            await liquipedia_client.close()


@dataclass(frozen=True)
class DailyBriefingResult:
    path: Path
    briefing_url: str
    skipped: bool = False


def build_briefing_url(web_base_url: str, briefing_date: date) -> str:
    return f"{web_base_url.rstrip('/')}/briefings/{briefing_date.isoformat()}.html"


async def run_daily_briefing(
    target_date: date | None = None, *, force: bool = False
) -> DailyBriefingResult | None:
    pipeline_start = time.monotonic()
    config = load_config()
    briefing_date = target_date or date.today()
    output_path = briefing_path_for_date(briefing_date)
    briefing_url = build_briefing_url(config.web_base_url, briefing_date)

    if output_path.exists() and not force:
        logger.info("Briefing already exists at %s; skipping", output_path)
        return DailyBriefingResult(
            path=output_path,
            briefing_url=briefing_url,
            skipped=True,
        )

    # 1. Collect
    logger.info("=== Step 1/4: Collecting ===")
    items = await run_collectors()

    # Social posts and upcoming-match cards bypass the LLM digest; they are
    # short, self-contained, and rendered in their own template blocks.
    social_items = [i for i in items if i.type == "social"]
    upcoming_items = [i for i in items if i.type == "upcoming"]
    digest_items = [i for i in items if i.type not in {"social", "upcoming"}]

    # 2. Editorial
    logger.info("=== Step 2/4: Editorial ===")
    t0 = time.monotonic()
    llm_cfg = config.llm
    provider_cfg = llm_cfg.providers.get(llm_cfg.default_provider)
    if not provider_cfg:
        logger.error("No LLM provider configured; aborting")
        return None

    provider = GeminiProvider(
        model=provider_cfg.model,
        api_key=provider_cfg.api_key_env,
    )
    try:
        digest = await generate_digest(digest_items, provider)
        logger.info(
            "Editorial done in %.1fs; summary: %s",
            time.monotonic() - t0,
            digest.summary_line,
        )
    except Exception:
        logger.exception(
            "Editorial step failed; falling back to unannotated digest so HTML still renders"
        )
        from overpass.editorial.digest import SECTION_NAMES, DigestOutput, SectionOutput, _group_items

        groups = _group_items(digest_items)
        sections = {
            SECTION_NAMES.get(k, k.title()): SectionOutput(intro="", items=v)
            for k, v in groups.items()
        }
        digest = DigestOutput(
            summary_line="Daily CS2 briefing (editorial unavailable).",
            sections=sections,
        )

    # 3. HTML briefing
    logger.info("=== Step 3/4: Rendering HTML ===")
    t0 = time.monotonic()
    this_day = get_primary_for(briefing_date)
    if this_day is not None:
        logger.info("This Day in CS: %d - %s", this_day.year, this_day.headline)
    else:
        logger.info("This Day in CS: no entry for %s", briefing_date.isoformat())
    html = render_briefing(
        digest,
        briefing_date,
        social_items=social_items,
        upcoming_items=upcoming_items,
        this_day=this_day,
    )
    path = save_briefing(html, briefing_date)
    logger.info("HTML saved to %s (%.1fs)", path, time.monotonic() - t0)

    # 4. Telegram notification
    logger.info("=== Step 4/4: Telegram notification ===")
    t0 = time.monotonic()
    await send_digest_notification(digest.summary_line, briefing_url)
    logger.info("Notification step done in %.1fs", time.monotonic() - t0)

    logger.info(
        "=== Pipeline complete in %.1fs ===",
        time.monotonic() - pipeline_start,
    )
    return DailyBriefingResult(path=path, briefing_url=briefing_url, skipped=False)
