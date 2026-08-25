from __future__ import annotations

import asyncio
import logging

import pytest

from vcf_mcp.upstream_control import UpstreamControl


@pytest.mark.asyncio
async def test_concurrency_is_bounded_per_backend() -> None:
    control = UpstreamControl(
        backend_name="fixture",
        target_id="target",
        max_concurrency=2,
    )
    active = 0
    maximum = 0
    release = asyncio.Event()

    async def worker() -> None:
        nonlocal active, maximum
        async with control.slot():
            active += 1
            maximum = max(maximum, active)
            await release.wait()
            active -= 1

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    await asyncio.sleep(0)
    assert maximum == 2
    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_429_backoff_is_exponential_bounded_and_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    delays: list[float] = []

    async def capture_sleep(delay: float) -> None:
        delays.append(delay)

    control = UpstreamControl(
        backend_name="fixture",
        target_id="target",
        max_429_retries=2,
        sleep=capture_sleep,
    )
    with caplog.at_level(logging.WARNING):
        assert await control.backoff_for_429(attempt=0, retry_after=None)
        assert await control.backoff_for_429(attempt=1, retry_after="1.25")
        assert not await control.backoff_for_429(attempt=2, retry_after=None)

    assert delays == [0.25, 1.25]
    assert caplog.text.count("upstream rate limiting activated") == 1
