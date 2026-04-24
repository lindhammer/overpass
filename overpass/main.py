"""Overpass entry point – end-to-end pipeline: collect → editorial → deliver."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

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
from overpass.delivery.html import render_briefing, save_briefing
from overpass.delivery.telegram import send_digest_notification
from overpass.editorial.digest import generate_digest
from overpass.editorial.gemini import GeminiProvider
from overpass.history.lookup import get_primary_for
from overpass.hltv.browser import HLTVBrowserClient
from overpass.liquipedia.client import LiquipediaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("overpass")

# ── Collector registry ───────────────────────────────────────────
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


COLLECTORS: list[BaseCollector] = build_collectors()


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
                logger.info("  %-10s → %d items", collector.name, len(result))
                items.extend(result)

        logger.info("Total items collected: %d", len(items))
        return items
    finally:
        await hltv_browser_client.close()
        if liquipedia_client is not None:
            await liquipedia_client.close()


async def async_main() -> None:
    pipeline_start = time.monotonic()
    config = load_config()

    # ── 1. Collect ───────────────────────────────────────────────
    logger.info("=== Step 1/4: Collecting ===")
    items = await run_collectors()

    # Social posts and upcoming-match cards bypass the LLM digest – they are
    # short, self-contained, and rendered in their own template blocks.
    social_items = [i for i in items if i.type == "social"]
    upcoming_items = [i for i in items if i.type == "upcoming"]
    digest_items = [i for i in items if i.type not in {"social", "upcoming"}]

    # ── 2. Editorial ─────────────────────────────────────────────
    logger.info("=== Step 2/4: Editorial ===")
    t0 = time.monotonic()
    llm_cfg = config.llm
    provider_cfg = llm_cfg.providers.get(llm_cfg.default_provider)
    if not provider_cfg:
        logger.error("No LLM provider configured – aborting")
        return

    provider = GeminiProvider(
        model=provider_cfg.model,
        api_key=provider_cfg.api_key_env,
    )
    try:
        digest = await generate_digest(digest_items, provider)
        logger.info(
            "Editorial done in %.1fs – summary: %s",
            time.monotonic() - t0,
            digest.summary_line,
        )
    except Exception:
        logger.exception(
            "Editorial step failed – falling back to unannotated digest so HTML still renders"
        )
        from overpass.editorial.digest import _group_items, DigestOutput, SectionOutput, SECTION_NAMES

        groups = _group_items(digest_items)
        sections = {
            SECTION_NAMES.get(k, k.title()): SectionOutput(intro="", items=v)
            for k, v in groups.items()
        }
        digest = DigestOutput(
            summary_line="Daily CS2 briefing (editorial unavailable).",
            sections=sections,
        )

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
    path = save_briefing(html, today)
    logger.info("HTML saved to %s (%.1fs)", path, time.monotonic() - t0)

    # ── 4. Telegram notification ─────────────────────────────────
    logger.info("=== Step 4/4: Telegram notification ===")
    t0 = time.monotonic()
    briefing_url = f"{config.web_base_url}/briefings/{today.isoformat()}.html"
    await send_digest_notification(digest.summary_line, briefing_url)
    logger.info("Notification step done in %.1fs", time.monotonic() - t0)

    logger.info(
        "=== Pipeline complete in %.1fs ===",
        time.monotonic() - pipeline_start,
    )


def main() -> None:
    """Sync wrapper for CLI entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
