"""Per-backend concurrency and bounded 429 backoff controls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager


DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_MAX_429_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.25
MAX_RETRY_AFTER_SECONDS = 30.0


class UpstreamControl:
    """Bound concurrent work and coordinate visible, bounded 429 retries."""

    def __init__(
        self,
        *,
        backend_name: str,
        target_id: str,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_429_retries: int = DEFAULT_MAX_429_RETRIES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("upstream concurrency limit must be positive")
        if max_429_retries < 0:
            raise ValueError("429 retry limit cannot be negative")
        self._slots = asyncio.Semaphore(max_concurrency)
        self._backend_name = backend_name
        self._target_id = target_id
        self._max_429_retries = max_429_retries
        self._sleep = sleep
        self._logger = logger or logging.getLogger(__name__)
        self._logged_first_429 = False

    @asynccontextmanager
    async def slot(self):
        async with self._slots:
            yield

    async def acquire(self) -> None:
        await self._slots.acquire()

    def release(self) -> None:
        self._slots.release()

    async def backoff_for_429(
        self, *, attempt: int, retry_after: str | None
    ) -> bool:
        """Sleep before another attempt, or return False when budget is spent."""

        if not self._logged_first_429:
            self._logger.warning(
                "upstream rate limiting activated for backend %s target %s",
                self._backend_name,
                self._target_id,
            )
            self._logged_first_429 = True
        if attempt >= self._max_429_retries:
            return False
        delay = min(
            _retry_after_seconds(retry_after)
            or DEFAULT_BACKOFF_SECONDS * (2**attempt),
            MAX_RETRY_AFTER_SECONDS,
        )
        await self._sleep(delay)
        return True


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
