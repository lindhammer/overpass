from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from overpass.worker import async_main, next_daily_run, parse_daily_time, seconds_until


def test_parse_daily_time_accepts_hour_and_minute():
    assert parse_daily_time("07:30").hour == 7
    assert parse_daily_time("07:30").minute == 30


def test_next_daily_run_uses_same_day_when_time_is_future():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 4, 26, 6, 0, tzinfo=tz)

    result = next_daily_run(now, "07:00", tz)

    assert result == datetime(2026, 4, 26, 7, 0, tzinfo=tz)


def test_next_daily_run_uses_next_day_when_time_has_passed():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 4, 26, 8, 0, tzinfo=tz)

    result = next_daily_run(now, "07:00", tz)

    assert result == datetime(2026, 4, 27, 7, 0, tzinfo=tz)


def test_seconds_until_uses_real_elapsed_time_across_dst_start():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 3, 28, 7, 0, tzinfo=tz)
    target = datetime(2026, 3, 29, 7, 0, tzinfo=tz)

    assert seconds_until(now, target) == 23 * 60 * 60


@pytest.mark.asyncio
async def test_run_now_executes_once_and_exits(monkeypatch):
    calls = []

    async def fake_run_daily_briefing(*, force):
        calls.append(force)

    monkeypatch.setattr("overpass.worker.run_daily_briefing", fake_run_daily_briefing)

    await async_main(["--run-now"])

    assert calls == [True]
