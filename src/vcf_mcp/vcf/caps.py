"""Result caps for the read plane, and how their numbers were derived.

Amendment 2 ruling 1 makes the numeric metrics cap this slice's to derive,
declare, test, and carry into the Gate 1 packet. This module is that
declaration. Every number below is traceable to a measurement against
``vcf-lab-operations-devel.int.sentania.net`` on 2026-07-25.

Two different postures, on purpose:

- **Lists clamp.** A page size above the server-owned maximum is reduced and
  the effective value is reported back with cursor metadata. Paging is lossless
  and resumable, so clamping loses nothing.
- **Metrics refuse.** A metrics request over the cap raises
  ``ResultCapExceeded`` naming the cap and the requested magnitude. A silently
  truncated series is worse than no series: it is indistinguishable from a
  quiet period in the data, and a caller cannot tell that it is reasoning about
  a fragment.

Derivation of ``METRICS_CELL_CAP``. A cell is one (resource, stat key, sample)
triple. Measured payload for ``POST /api/resources/stats/query`` at a 5-minute
rollup:

===========================  ==========  ===========  ==============
request                      samples     bytes        bytes per cell
===========================  ==========  ===========  ==============
1 resource, 1 key, 1 hour    12          535          ~45 (envelope dominated)
1 resource, 1 key, 24 hours  286         7,485        ~26
5 resources, 20 keys, 24 h   286 each    603,732      ~21
===========================  ==========  ===========  ==============

So a cell costs roughly 20 to 26 bytes of upstream JSON and roughly 6 tokens
once projected to timestamp and value pairs. Record 001 measured a 274,000
token blowup as the thing to prevent. A ceiling of about 30,000 tokens per
metrics call, which is a large but survivable fraction of a client context,
gives 30,000 / 6, so **5,000 cells**. The sub-caps below bound the individual
factors so a request cannot reach the cell cap through one absurd dimension.

**Measured, and load bearing: ``maxSamples`` is ignored by this appliance.**
Sending ``maxSamples: 1`` and ``maxSamples: 10`` for the same resource, key,
and window returns byte-identical 7,485 byte responses containing 286 samples.
Sample count is determined by ``begin``, ``end``, and the interval, and by
nothing else. That is why the cap is computed here from the window and the
interval rather than trusted from a request field, and why the ranged-stats
adapter requires an explicit window.
"""

from __future__ import annotations

import math

from vcf_mcp.contracts import TargetId
from vcf_mcp.vcf.errors import ResultCapExceeded


# Lists. Server-owned maximum page size; a larger request is clamped.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Metrics. Refusal, not truncation.
METRICS_CELL_CAP = 5_000
MAX_METRICS_RESOURCES = 50
MAX_METRICS_STAT_KEYS = 25
MAX_METRICS_SAMPLES_PER_SERIES = 1_000

# A guard on what the appliance sends us, independent of what we asked for. An
# unfiltered ``GET /api/resources`` measured 1,115,211 bytes, so eight
# mebibytes is roughly seven times the largest collection this appliance can
# currently produce and still bounds a pathological response.
MAX_UPSTREAM_RESPONSE_BYTES = 8 * 1024 * 1024

_INTERVAL_SECONDS = {
    "SECONDS": 1,
    "MINUTES": 60,
    "HOURS": 3600,
    "DAYS": 86_400,
    "WEEKS": 604_800,
    "MONTHS": 2_592_000,
    "YEARS": 31_536_000,
}


def clamp_page_size(requested: int | None) -> int:
    """Reduce a requested page size to the server-owned maximum."""

    if requested is None:
        return DEFAULT_PAGE_SIZE
    if requested < 1:
        return 1
    return min(int(requested), MAX_PAGE_SIZE)


def interval_seconds(interval_type: str, quantifier: int) -> int:
    """Length of one sample interval, refusing an interval this API lacks."""

    unit = _INTERVAL_SECONDS.get(interval_type.upper())
    if unit is None or quantifier < 1:
        raise ValueError(f"unsupported sampling interval {interval_type!r}")
    return unit * int(quantifier)


def samples_in_window(
    *, begin_ms: int, end_ms: int, interval_type: str, quantifier: int
) -> int:
    """Sample count implied by a window and an interval.

    Computed rather than requested, because ``maxSamples`` is ignored by this
    appliance (see the module docstring).
    """

    if end_ms <= begin_ms:
        raise ValueError("the metrics window must end after it begins")
    span_seconds = (end_ms - begin_ms) / 1000.0
    return math.floor(span_seconds / interval_seconds(interval_type, quantifier)) + 1


def enforce_metrics_cap(
    *,
    resource_count: int,
    stat_key_count: int,
    sample_count: int,
    target_id: TargetId | None = None,
) -> int:
    """Refuse an over-cap metrics read, naming the cap that refused it.

    Returns the cell count when the request is within every cap, so a caller
    can record it.
    """

    if resource_count < 1 or stat_key_count < 1 or sample_count < 1:
        raise ValueError("a metrics read needs at least one resource, key, and sample")
    if resource_count > MAX_METRICS_RESOURCES:
        raise ResultCapExceeded(
            cap_name="MAX_METRICS_RESOURCES",
            cap_value=MAX_METRICS_RESOURCES,
            requested=resource_count,
            unit="resources",
            target_id=target_id,
        )
    if stat_key_count > MAX_METRICS_STAT_KEYS:
        raise ResultCapExceeded(
            cap_name="MAX_METRICS_STAT_KEYS",
            cap_value=MAX_METRICS_STAT_KEYS,
            requested=stat_key_count,
            unit="stat keys",
            target_id=target_id,
        )
    if sample_count > MAX_METRICS_SAMPLES_PER_SERIES:
        raise ResultCapExceeded(
            cap_name="MAX_METRICS_SAMPLES_PER_SERIES",
            cap_value=MAX_METRICS_SAMPLES_PER_SERIES,
            requested=sample_count,
            unit="samples per series",
            target_id=target_id,
        )
    cells = resource_count * stat_key_count * sample_count
    if cells > METRICS_CELL_CAP:
        raise ResultCapExceeded(
            cap_name="METRICS_CELL_CAP",
            cap_value=METRICS_CELL_CAP,
            requested=cells,
            unit="cells (resources x stat keys x samples)",
            target_id=target_id,
        )
    return cells


def enforce_response_size(
    *, byte_count: int, target_id: TargetId | None = None
) -> None:
    """Refuse a response larger than the upstream guard."""

    if byte_count > MAX_UPSTREAM_RESPONSE_BYTES:
        raise ResultCapExceeded(
            cap_name="MAX_UPSTREAM_RESPONSE_BYTES",
            cap_value=MAX_UPSTREAM_RESPONSE_BYTES,
            requested=byte_count,
            unit="bytes",
            target_id=target_id,
        )
