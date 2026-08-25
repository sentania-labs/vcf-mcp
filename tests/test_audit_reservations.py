import asyncio
import unittest

from vcf_mcp.dispatcher.reservations import (
    CALL_RESERVATION_BYTES,
    CHECKPOINT_HEADROOM_BYTES,
    FreeSpaceReservations,
    InsufficientAuditSpace,
)


class FreeSpaceReservationTests(unittest.IsolatedAsyncioTestCase):
    def test_numeric_derivation_is_pinned(self) -> None:
        self.assertEqual(CALL_RESERVATION_BYTES, 32_960)
        self.assertEqual(CHECKPOINT_HEADROOM_BYTES, 8_216_000)

    async def test_concurrent_calls_consume_and_release_reservations(self) -> None:
        capacity = CHECKPOINT_HEADROOM_BYTES + 2 * CALL_RESERVATION_BYTES
        reservations = FreeSpaceReservations(lambda: capacity)
        first, second = await asyncio.gather(
            reservations.acquire(),
            reservations.acquire(),
        )
        self.assertEqual(reservations.reserved_bytes, 2 * CALL_RESERVATION_BYTES)
        with self.assertRaises(InsufficientAuditSpace):
            await reservations.acquire()

        await first.release()
        third = await reservations.acquire()
        self.assertEqual(reservations.reserved_bytes, 2 * CALL_RESERVATION_BYTES)
        await asyncio.gather(second.release(), third.release())
        self.assertEqual(reservations.reserved_bytes, 0)

    async def test_checkpoint_headroom_is_never_admitted_into(self) -> None:
        reservations = FreeSpaceReservations(
            lambda: CHECKPOINT_HEADROOM_BYTES + CALL_RESERVATION_BYTES - 1
        )
        with self.assertRaises(InsufficientAuditSpace):
            await reservations.acquire()

    async def test_release_is_idempotent(self) -> None:
        reservations = FreeSpaceReservations(
            lambda: CHECKPOINT_HEADROOM_BYTES + CALL_RESERVATION_BYTES
        )
        lease = await reservations.acquire()
        await lease.release()
        await lease.release()
        self.assertEqual(reservations.reserved_bytes, 0)


if __name__ == "__main__":
    unittest.main()
