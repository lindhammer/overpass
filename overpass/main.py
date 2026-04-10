"""Overpass entry point – runs all registered collectors and dumps JSON."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.collectors.podcast import PodcastCollector
from overpass.collectors.reddit import RedditCollector
from overpass.collectors.steam import SteamCollector
from overpass.collectors.youtube import YouTubeCollector
from overpass.config import load_config
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
    """Run every registered collector concurrently and merge results."""
    config = load_config()
    logger.info("Timezone: %s", config.tz)
    logger.info("Registered collectors: %d", len(COLLECTORS))

    if not COLLECTORS:
        logger.warning("No collectors registered yet – nothing to collect.")
        return []

    results = await asyncio.gather(
        *(c.collect() for c in COLLECTORS),
        return_exceptions=True,
    )

    items: list[CollectorItem] = []
    for collector, result in zip(COLLECTORS, results):
        if isinstance(result, BaseException):
            logger.error("Collector %s failed: %s", collector.name, result)
        else:
            logger.info("Collector %s returned %d items", collector.name, len(result))
            items.extend(result)

    return items


async def async_main() -> None:
    config = load_config()
    items = await run_collectors()

    # ── Editorial layer ──────────────────────────────────────────
    llm_cfg = config.llm
    provider_cfg = llm_cfg.providers.get(llm_cfg.default_provider)
    if provider_cfg:
        provider = GeminiProvider(
            model=provider_cfg.model,
            api_key=provider_cfg.api_key_env,  # resolved to actual key by config loader
        )
        digest = await generate_digest(items, provider)
        output = digest.model_dump(mode="json")
    else:
        logger.warning("No LLM provider configured – dumping raw items")
        output = [item.model_dump(mode="json") for item in items]

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    print()  # trailing newline


def main() -> None:
    """Sync wrapper for CLI entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
