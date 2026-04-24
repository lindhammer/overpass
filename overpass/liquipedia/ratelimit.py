"""Global async rate limiter — enforces a minimum interval between calls."""

from __future__ import annotations

import asyncio


class AsyncRateLimiter:
    """Serialize async callers with a minimum interval between acquisitions."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = float(min_interval)
        self._lock = asyncio.Lock()
        self._last_at: float | None = None

    async def acquire(self) -> None:
        """Wait until the next request slot is available."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            if self._last_at is not None:
                wait = self._min_interval - (loop.time() - self._last_at)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_at = loop.time()
