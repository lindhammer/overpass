"""One-off live smoke test for the Nitter social collector.

Run with: python tools/smoke_social.py
Not part of the pytest suite — hits real public Nitter instances.
"""

from __future__ import annotations

import asyncio
import logging

import overpass.collectors.social as social_mod
from overpass.collectors.social import NitterSocialCollector
from overpass.config import AppConfig, SocialConfig, SocialHandle

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def _make_cfg() -> SocialConfig:
    return SocialConfig(
        enabled=True,
        handles=[
            SocialHandle(handle="s1mpleO", display_name="s1mple"),
            SocialHandle(handle="ZywOo", display_name="ZywOo"),
            SocialHandle(handle="donk_s1", display_name="donk"),
            SocialHandle(handle="karrigan", display_name="karrigan"),
            SocialHandle(handle="ropz", display_name="ropz"),
        ],
        # Widen window so the smoke test isn't dependent on whether each pro
        # actually posted in the last 24 hours.
        lookback_hours=24 * 30,
        max_per_handle=3,
        max_total_posts=15,
        request_timeout_seconds=10,
    )


async def main() -> None:
    cfg = _make_cfg()
    base = AppConfig().model_copy(update={"social": cfg})
    social_mod.load_config = lambda: base

    items = await NitterSocialCollector().collect()
    print(f"\n=== {len(items)} items ===\n")
    for it in items:
        handle = it.metadata["handle"]
        body = it.metadata["body"][:100].replace("\n", " ")
        print(f"@{handle:15s}  {it.timestamp.isoformat()}  {body}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
