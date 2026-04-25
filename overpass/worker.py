"""Always-on Overpass worker for scheduled daily briefings."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, time as daily_time, timedelta
from zoneinfo import ZoneInfo

from overpass.config import load_config
from overpass.pipeline import run_daily_briefing

logger = logging.getLogger("overpass.worker")


def parse_daily_time(value: str) -> daily_time:
    """Parse a daily HH:MM schedule value."""
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
        return daily_time(hour=hour, minute=minute)
    except ValueError as exc:
        raise ValueError(f"daily schedule must use HH:MM format, got {value!r}") from exc


def next_daily_run(now: datetime, schedule: str, tz: ZoneInfo) -> datetime:
    """Return the next scheduled daily run time in the configured timezone."""
    local_now = now.astimezone(tz)
    target_time = parse_daily_time(schedule)
    candidate = datetime.combine(local_now.date(), target_time, tzinfo=tz)
    if candidate <= local_now:
        candidate = candidate + timedelta(days=1)
    return candidate


def seconds_until(now: datetime, target: datetime) -> float:
    """Return real elapsed seconds from now until target."""
    return max(0.0, target.timestamp() - now.timestamp())


async def run_scheduler() -> None:
    """Run the daily briefing scheduler forever."""
    config = load_config()
    tz = config.tz
    schedule = config.schedule.daily_digest
    logger.info("Starting Overpass worker; daily briefing schedule=%s timezone=%s", schedule, config.timezone)

    while True:
        now = datetime.now(tz)
        run_at = next_daily_run(now, schedule, tz)
        sleep_seconds = seconds_until(now, run_at)
        logger.info("Next daily briefing scheduled for %s", run_at.isoformat())
        await asyncio.sleep(sleep_seconds)

        try:
            result = await run_daily_briefing(run_at.date(), force=False)
        except Exception:
            logger.exception("Scheduled daily briefing failed")
            continue

        if result is None:
            logger.error("Scheduled daily briefing did not complete")
        elif result.skipped:
            logger.info("Scheduled daily briefing skipped; existing output at %s", result.path)
        else:
            logger.info("Scheduled daily briefing generated at %s", result.path)


async def async_main(argv: list[str] | None = None) -> None:
    """Async worker CLI entry point."""
    parser = argparse.ArgumentParser(description="Overpass always-on worker")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run one briefing immediately, bypass duplicate-output checks, and exit",
    )
    args = parser.parse_args(argv)

    if args.run_now:
        await run_daily_briefing(force=True)
        return

    await run_scheduler()


def main() -> None:
    """Sync wrapper for the worker CLI."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
