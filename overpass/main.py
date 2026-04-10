"""Overpass entry point – end-to-end pipeline: collect → editorial → deliver."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.collectors.podcast import PodcastCollector
from overpass.collectors.reddit import RedditCollector
from overpass.collectors.steam import SteamCollector
from overpass.collectors.youtube import YouTubeCollector
from overpass.config import load_config
from overpass.delivery.html import render_briefing, save_briefing
from overpass.delivery.telegram import send_digest_notification
from overpass.editorial.digest import generate_digest
from overpass.editorial.gemini import GeminiProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("overpass")

# ── Collector registry ───────────────────────────────────────────
COLLECTORS: list[BaseCollector] = [
    PodcastCollector(),
    RedditCollector(),
    SteamCollector(),
    YouTubeCollector(),
]


async def run_collectors() -> list[CollectorItem]:
    """Run every registered collector concurrently; log per-collector counts."""
    config = load_config()
    logger.info("Timezone: %s", config.tz)
    logger.info("Running %d collectors", len(COLLECTORS))

    t0 = time.monotonic()
    results = await asyncio.gather(
        *(c.collect() for c in COLLECTORS),
        return_exceptions=True,
    )
    logger.info("Collectors finished in %.1fs", time.monotonic() - t0)

    items: list[CollectorItem] = []
    for collector, result in zip(COLLECTORS, results):
        if isinstance(result, BaseException):
            logger.error("Collector %s failed: %s", collector.name, result)
        else:
            logger.info("  %-10s → %d items", collector.name, len(result))
            items.extend(result)

    logger.info("Total items collected: %d", len(items))
    return items


async def async_main() -> None:
    pipeline_start = time.monotonic()
    config = load_config()

    # ── 1. Collect ───────────────────────────────────────────────
    logger.info("=== Step 1/4: Collecting ===")
    items = await run_collectors()

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
    digest = await generate_digest(items, provider)
    logger.info("Editorial done in %.1fs – summary: %s", time.monotonic() - t0, digest.summary_line)

    # ── 3. HTML briefing ─────────────────────────────────────────
    logger.info("=== Step 3/4: Rendering HTML ===")
    t0 = time.monotonic()
    today = date.today()
    html = render_briefing(digest, today)
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
