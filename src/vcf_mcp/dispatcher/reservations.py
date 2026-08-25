"""Numeric free-space accounting for audited call admission."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass


SQLITE_PAGE_BYTES = 4096
WAL_FRAME_HEADER_BYTES = 24
WAL_AUTOCHECKPOINT_FRAMES = 1000
DIRTY_PAGES_PER_AUDIT_RECORD = 4
AUDIT_RECORDS_PER_CALL = 2

# A checkpoint can temporarily require both the WAL frames and their database
# pages. Keep that full amount free even when no calls are in flight.
CHECKPOINT_HEADROOM_BYTES = WAL_AUTOCHECKPOINT_FRAMES * (
    SQLITE_PAGE_BYTES + WAL_FRAME_HEADER_BYTES + SQLITE_PAGE_BYTES
)

# Each admitted call owes an attempt and a terminal record. Four dirty pages per
# record covers the audit table plus three indexes. Retaining the whole amount
# until terminal completion deliberately double-counts the committed attempt.
CALL_RESERVATION_BYTES = (
    AUDIT_RECORDS_PER_CALL
    * DIRTY_PAGES_PER_AUDIT_RECORD
    * (SQLITE_PAGE_BYTES + WAL_FRAME_HEADER_BYTES)
)


class InsufficientAuditSpace(Exception):
    """Raised before admission when the numeric audit reserve cannot be held."""


@dataclass(slots=True)
class ReservationLease:
    _owner: FreeSpaceReservations
    _released: bool = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._owner._release()

    async def __aenter__(self) -> ReservationLease:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.release()


class FreeSpaceReservations:
    """Serialize admission and account for every concurrently admitted call."""

    def __init__(self, available_bytes: Callable[[], int]) -> None:
        self._available_bytes = available_bytes
        self._reserved_bytes = 0
        self._lock = asyncio.Lock()

    @property
    def reserved_bytes(self) -> int:
        return self._reserved_bytes

    async def acquire(self) -> ReservationLease:
        async with self._lock:
            required = (
                CHECKPOINT_HEADROOM_BYTES
                + self._reserved_bytes
                + CALL_RESERVATION_BYTES
            )
            if self._available_bytes() < required:
                raise InsufficientAuditSpace
            self._reserved_bytes += CALL_RESERVATION_BYTES
        return ReservationLease(self)

    async def _release(self) -> None:
        async with self._lock:
            self._reserved_bytes -= CALL_RESERVATION_BYTES
            if self._reserved_bytes < 0:
                raise RuntimeError("audit reservation accounting underflow")
