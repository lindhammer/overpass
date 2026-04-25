"""Overpass one-shot CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging

from overpass.pipeline import build_collectors, run_daily_briefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("overpass")

try:
    COLLECTORS = build_collectors()
except Exception:
    COLLECTORS = []


async def async_main() -> None:
    await run_daily_briefing(force=True)


def main() -> None:
    """Sync wrapper for CLI entry point."""
    parser = argparse.ArgumentParser(description="Overpass CS2 daily briefing")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate a demo briefing from mock data, no config required",
    )
    args = parser.parse_args()

    if args.demo:
        from overpass.demo import run_demo

        run_demo()
        return

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
