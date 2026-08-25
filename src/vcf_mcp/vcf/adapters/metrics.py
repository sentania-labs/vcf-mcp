"""Metrics adapters: stat key discovery, latest stats, ranged stats, super metrics.

This is the payload blowup risk in the whole read surface, and two measured
facts shape every adapter here.

**``maxSamples`` is ignored.** ``POST /api/resources/stats/query`` returns
byte-identical 7,485 byte responses containing 286 samples for ``maxSamples: 1``
and ``maxSamples: 10``. Sample count follows ``begin``, ``end``, and the
interval, and nothing else. So ``maxSamples`` is deliberately absent from the
permitted body keys: permitting a field that does nothing would let a caller
believe it had bounded a response it had not bounded. The window is required
instead, and the cap is computed from it.

**Stat keys must be named.** One resource with no key filter returned 24,967
bytes across 237 keys on ``stats/latest``, and the key count for a resource is
not knowable before the call. Both stats adapters therefore require an explicit
non-empty key list, which is what ``discover_stat_keys`` exists to produce.

Caps refuse, they never truncate. See ``caps.py`` for the derivation of the
numbers and their measurements.
"""

from __future__ import annotations

from collections.abc import Sequence

from vcf_mcp.contracts import Capability, HttpMethod, JsonObject, OutboundContract
from vcf_mcp.vcf import projection
from vcf_mcp.vcf.adapters.base import ReadAdapter
from vcf_mcp.vcf.caps import (
    clamp_page_size,
    enforce_metrics_cap,
    samples_in_window,
)
from vcf_mcp.vcf.client import VcfTargetClient
from vcf_mcp.vcf.outbound import ReadContract


STAT_KEYS = ReadContract(
    name="metrics.stat_keys",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/resources/{resource_id}/statkeys",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.STAT_KEY_PROJECTION_VERSION,
)

LATEST_STATS = ReadContract(
    name="metrics.latest_stats",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/resources/stats/latest",
        permitted_query_parameters=frozenset({"resourceId", "statKey"}),
    ),
    projection_version=projection.STATS_PROJECTION_VERSION,
)

RANGED_STATS = ReadContract(
    name="metrics.ranged_stats",
    contract=OutboundContract(
        method=HttpMethod.POST,
        path_template="/api/resources/stats/query",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.STATS_PROJECTION_VERSION,
    # maxSamples is measured to be ignored by this appliance and is refused
    # here rather than sent and trusted.
    permitted_body_keys=frozenset(
        {
            "resourceId",
            "statKey",
            "intervalType",
            "intervalQuantifier",
            "rollUpType",
            "begin",
            "end",
        }
    ),
)

SUPER_METRICS = ReadContract(
    name="metrics.super_metrics",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/supermetrics",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.SUPER_METRIC_PROJECTION_VERSION,
)

SUPER_METRIC_DETAIL = ReadContract(
    name="metrics.super_metric_detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/supermetrics/{super_metric_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.SUPER_METRIC_PROJECTION_VERSION,
)

DEFAULT_INTERVAL_TYPE = "MINUTES"
DEFAULT_INTERVAL_QUANTIFIER = 5
DEFAULT_ROLL_UP_TYPE = "AVG"


async def discover_stat_keys(
    client: VcfTargetClient, *, resource_id: str
) -> JsonObject:
    body = await client.request_read(
        STAT_KEYS, path_parameters={"resource_id": resource_id}
    )
    return projection.collection(
        body,
        envelope_key="stat-key",
        projector=projection.stat_key,
        projection_version=STAT_KEYS.projection_version,
    )


async def get_latest_stats(
    client: VcfTargetClient,
    *,
    resource_ids: Sequence[str],
    stat_keys: Sequence[str],
) -> JsonObject:
    resource_ids = list(resource_ids)
    stat_keys = list(stat_keys)
    cells = enforce_metrics_cap(
        resource_count=len(resource_ids),
        stat_key_count=len(stat_keys),
        sample_count=1,
        target_id=client.target_id,
    )
    body = await client.request_read(
        LATEST_STATS,
        query={"resourceId": resource_ids, "statKey": stat_keys},
    )
    projected = dict(projection.stats(body))
    projected["requested_cells"] = cells
    return projected


async def get_ranged_stats(
    client: VcfTargetClient,
    *,
    resource_ids: Sequence[str],
    stat_keys: Sequence[str],
    begin_ms: int,
    end_ms: int,
    interval_type: str = DEFAULT_INTERVAL_TYPE,
    interval_quantifier: int = DEFAULT_INTERVAL_QUANTIFIER,
    roll_up_type: str = DEFAULT_ROLL_UP_TYPE,
) -> JsonObject:
    resource_ids = list(resource_ids)
    stat_keys = list(stat_keys)
    samples = samples_in_window(
        begin_ms=begin_ms,
        end_ms=end_ms,
        interval_type=interval_type,
        quantifier=interval_quantifier,
    )
    cells = enforce_metrics_cap(
        resource_count=len(resource_ids),
        stat_key_count=len(stat_keys),
        sample_count=samples,
        target_id=client.target_id,
    )
    body = await client.request_read(
        RANGED_STATS,
        body={
            "resourceId": resource_ids,
            "statKey": stat_keys,
            "intervalType": interval_type,
            "intervalQuantifier": interval_quantifier,
            "rollUpType": roll_up_type,
            "begin": begin_ms,
            "end": end_ms,
        },
    )
    projected = dict(projection.stats(body))
    projected["requested_cells"] = cells
    projected["requested_samples_per_series"] = samples
    return projected


async def list_super_metrics(
    client: VcfTargetClient, *, page: int = 0, page_size: int | None = None
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        SUPER_METRICS, query={"page": page, "pageSize": size}
    )
    return projection.collection(
        body,
        envelope_key="superMetrics",
        projector=projection.super_metric,
        projection_version=SUPER_METRICS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_super_metric(
    client: VcfTargetClient, *, super_metric_id: str
) -> JsonObject:
    body = await client.request_read(
        SUPER_METRIC_DETAIL, path_parameters={"super_metric_id": super_metric_id}
    )
    return {
        "super_metric": projection.super_metric(body),
        "projection_version": SUPER_METRIC_DETAIL.projection_version,
    }


ADAPTERS: tuple[ReadAdapter, ...] = (
    ReadAdapter(
        tool_name="discover_stat_keys",
        capability=Capability.READ_METRICS,
        read_contract=STAT_KEYS,
        handler=discover_stat_keys,
        summary="List the stat keys collected for one resource.",
    ),
    ReadAdapter(
        tool_name="get_latest_stats",
        capability=Capability.READ_METRICS,
        read_contract=LATEST_STATS,
        handler=get_latest_stats,
        summary="Latest value of named stat keys for named resources.",
    ),
    ReadAdapter(
        tool_name="get_ranged_stats",
        capability=Capability.READ_METRICS,
        read_contract=RANGED_STATS,
        handler=get_ranged_stats,
        summary="Rolled-up stat series over an explicit time window.",
    ),
    ReadAdapter(
        tool_name="list_super_metrics",
        capability=Capability.READ_METRICS,
        read_contract=SUPER_METRICS,
        handler=list_super_metrics,
        summary="List super metric definitions and their formulas.",
    ),
    ReadAdapter(
        tool_name="get_super_metric",
        capability=Capability.READ_METRICS,
        read_contract=SUPER_METRIC_DETAIL,
        handler=get_super_metric,
        summary="Fetch one super metric definition by id.",
    ),
)
