"""AsyncRateLimiter tests — enforces global min-interval, no overshoot."""

from __future__ import annotations

import asyncio

import pytest

from overpass.liquipedia.ratelimit import AsyncRateLimiter


def test_first_call_does_not_wait() -> None:
    limiter = AsyncRateLimiter(min_interval=0.05)
    elapsed = asyncio.run(_timed(limiter))
    assert elapsed < 0.04


def test_second_call_waits_at_least_interval() -> None:
    limiter = AsyncRateLimiter(min_interval=0.05)

    async def two_calls() -> float:
        loop = asyncio.get_event_loop()
        await limiter.acquire()
        start = loop.time()
        await limiter.acquire()
        return loop.time() - start

    elapsed = asyncio.run(two_calls())
    assert elapsed >= 0.045  # small clock slack


def test_concurrent_calls_are_serialised() -> None:
    limiter = AsyncRateLimiter(min_interval=0.03)

    async def run() -> list[float]:
        loop = asyncio.get_event_loop()
        timestamps: list[float] = []

        async def one() -> None:
            await limiter.acquire()
            timestamps.append(loop.time())

        await asyncio.gather(one(), one(), one())
        return timestamps

    ts = asyncio.run(run())
    ts.sort()
    # Each consecutive pair must be at least min_interval apart.
    assert ts[1] - ts[0] >= 0.025
    assert ts[2] - ts[1] >= 0.025


async def _timed(limiter: AsyncRateLimiter) -> float:
    loop = asyncio.get_event_loop()
    start = loop.time()
    await limiter.acquire()
    return loop.time() - start
