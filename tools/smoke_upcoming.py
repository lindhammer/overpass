"""Live smoke test for the HLTVUpcomingCollector."""

import asyncio
import logging

from overpass.collectors.hltv_upcoming import HLTVUpcomingCollector
from overpass.hltv.browser import HLTVBrowserClient
from overpass.config import load_config


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    cfg = load_config()
    browser = HLTVBrowserClient.from_config(cfg.hltv)
    try:
        collector = HLTVUpcomingCollector(browser_client=browser)
        items = await collector.collect()
        print(f"\n=== {len(items)} upcoming matches ===")
        for it in items:
            md = it.metadata
            print(
                f"  {md['starts_at']}  {md['team1']:>20s} vs {md['team2']:<20s}  "
                f"[{md.get('format') or '?'}]  {md.get('event') or ''}"
            )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
