"""Projections: what a caller sees, and what never leaves this process.

SPEC section 5. Every projection drops HATEOAS links, keeps stable
identifiers, names, kinds, state, and timestamps, and never exposes an upstream
endpoint name. Full fidelity is not a blanket flag: a caller cannot ask for the
unprojected object, which is what stops the 274,000 token response record 001
measured from being reachable.

Each projection carries a version string. The version is written to the audit
record, so a change in what a tool returned is visible after the fact rather
than inferred. Adding a field is a minor bump by convention; removing or
retyping one is a new major version and a client-visible change.

Envelope keys on this API are inconsistent and were verified independently by
two doers, then re-measured on 2026-07-25: ``adapter-kind``, ``resource-kind``,
``resourceList``, ``superMetrics``, ``alerts``, ``symptom`` (singular),
``alertDefinitions``, ``symptomDefinitions``, ``reportDefinitions``,
``reports``, ``stat-key``, ``values``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vcf_ops_mcp.vcf.errors import UpstreamProtocolError


RESOURCE_PROJECTION_VERSION = "resource.v1"
ADAPTER_KIND_PROJECTION_VERSION = "adapter_kind.v1"
RESOURCE_KIND_PROJECTION_VERSION = "resource_kind.v1"
STAT_KEY_PROJECTION_VERSION = "stat_key.v1"
STATS_PROJECTION_VERSION = "stats.v1"
SUPER_METRIC_PROJECTION_VERSION = "super_metric.v1"
ALERT_PROJECTION_VERSION = "alert.v1"
ALERT_DEFINITION_PROJECTION_VERSION = "alert_definition.v1"
SYMPTOM_PROJECTION_VERSION = "symptom.v1"
SYMPTOM_DEFINITION_PROJECTION_VERSION = "symptom_definition.v1"
REPORT_DEFINITION_PROJECTION_VERSION = "report_definition.v1"


def _require_object(value: object, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UpstreamProtocolError(f"expected {what} to be a JSON object")
    return value


def _require_list(value: object, what: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise UpstreamProtocolError(f"expected {what} to be a JSON array")
    return value


def collection(
    body: Mapping[str, Any],
    *,
    envelope_key: str,
    projector: Callable[[Mapping[str, Any]], dict[str, Any]],
    projection_version: str,
    requested_page: int = 0,
    requested_page_size: int | None = None,
) -> dict[str, Any]:
    """Project a paginated collection and compute honest cursor metadata.

    A ``NEXT`` link is present on this API even for a single-page result, so
    ``has_more`` is computed from the counts rather than read from the links.
    """

    items_raw = body.get(envelope_key)
    if items_raw is None:
        raise UpstreamProtocolError(
            f"the response is missing its {envelope_key!r} collection"
        )
    items = _require_list(items_raw, envelope_key)
    page_info = body.get("pageInfo")
    if isinstance(page_info, Mapping):
        total = page_info.get("totalCount")
        page = page_info.get("page", requested_page)
        page_size = page_info.get("pageSize", requested_page_size)
    else:
        total = None
        page = requested_page
        page_size = requested_page_size
    projected = [projector(_require_object(item, envelope_key)) for item in items]
    has_more = None
    if isinstance(total, int) and isinstance(page, int) and isinstance(page_size, int):
        has_more = (page + 1) * page_size < total
    return {
        "items": projected,
        "projection_version": projection_version,
        "page": page,
        "page_size": page_size,
        "total_count": total,
        "has_more": has_more,
    }


def resource(item: Mapping[str, Any]) -> dict[str, Any]:
    key = item.get("resourceKey")
    key = key if isinstance(key, Mapping) else {}
    identifiers = key.get("resourceIdentifiers")
    status_states = item.get("resourceStatusStates")
    states = []
    if isinstance(status_states, list):
        for state in status_states:
            if isinstance(state, Mapping):
                states.append(
                    {
                        "status": state.get("resourceStatus"),
                        "state": state.get("resourceState"),
                    }
                )
    return {
        "id": item.get("identifier"),
        "name": key.get("name"),
        "adapter_kind": key.get("adapterKindKey"),
        "resource_kind": key.get("resourceKindKey"),
        "identifiers": [
            {
                "name": entry.get("identifierType", {}).get("name")
                if isinstance(entry.get("identifierType"), Mapping)
                else None,
                "value": entry.get("value"),
            }
            for entry in identifiers
            if isinstance(entry, Mapping)
        ]
        if isinstance(identifiers, list)
        else [],
        "status_states": states,
        "health": item.get("resourceHealth"),
        "health_value": item.get("resourceHealthValue"),
        "created_at_ms": item.get("creationTime"),
    }


def adapter_kind(item: Mapping[str, Any]) -> dict[str, Any]:
    resource_kinds = item.get("resourceKinds")
    return {
        "key": item.get("key"),
        "name": item.get("name"),
        "description": item.get("description"),
        "adapter_kind_type": item.get("adapterKindType"),
        "resource_kind_count": len(resource_kinds)
        if isinstance(resource_kinds, list)
        else None,
    }


def resource_kind(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "key": item.get("key"),
        "name": item.get("name"),
        "adapter_kind": item.get("adapterKind"),
        "resource_kind_type": item.get("resourceKindType"),
    }


def stat_key(item: Mapping[str, Any]) -> dict[str, Any]:
    return {"stat_key": item.get("key")}


def super_metric(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "formula": item.get("formula"),
        "description": item.get("description"),
        "modified_at_ms": item.get("modificationTime"),
    }


def alert(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("alertId"),
        "resource_id": item.get("resourceId"),
        "level": item.get("alertLevel"),
        "status": item.get("status"),
        "control_state": item.get("controlState"),
        "impact": item.get("alertImpact"),
        "definition_id": item.get("alertDefinitionId"),
        "definition_name": item.get("alertDefinitionName"),
        "started_at_ms": item.get("startTimeUTC"),
        "updated_at_ms": item.get("updateTimeUTC"),
        "cancelled_at_ms": item.get("cancelTimeUTC"),
    }


def alert_definition(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "adapter_kind": item.get("adapterKindKey"),
        "resource_kind": item.get("resourceKindKey"),
        "wait_cycles": item.get("waitCycles"),
        "cancel_cycles": item.get("cancelCycles"),
    }


def symptom(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "resource_id": item.get("resourceId"),
        "definition_id": item.get("symptomDefinitionId"),
        "criticality": item.get("symptomCriticality"),
        "stat_key": item.get("statKey"),
        "message": item.get("message"),
        "kpi": item.get("kpi"),
        "started_at_ms": item.get("startTimeUTC"),
        "updated_at_ms": item.get("updateTimeUTC"),
        "cancelled_at_ms": item.get("cancelTimeUTC"),
    }


def symptom_definition(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "adapter_kind": item.get("adapterKindKey"),
        "resource_kind": item.get("resourceKindKey"),
        "state": item.get("state"),
        "wait_cycles": item.get("waitCycles"),
        "cancel_cycles": item.get("cancelCycles"),
    }


def report_definition(item: Mapping[str, Any]) -> dict[str, Any]:
    subject = item.get("subject")
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "owner": item.get("owner"),
        "active": item.get("active"),
        "subject": list(subject) if isinstance(subject, list) else None,
    }


def stats(body: Mapping[str, Any]) -> dict[str, Any]:
    """Project a stats response into flat per-resource, per-key series.

    Both ``stats/latest`` and ``stats/query`` return the same nested shape:
    ``values[].stat-list.stat[]`` with ``statKey.key``, ``timestamps``, and
    ``data``. ``stats/query`` adds ``rollUpType`` and ``intervalUnit``.
    """

    values = body.get("values")
    if values is None:
        raise UpstreamProtocolError("the stats response is missing its values")
    series: list[dict[str, Any]] = []
    samples = 0
    for entry in _require_list(values, "values"):
        entry = _require_object(entry, "a stats value")
        stat_list = entry.get("stat-list")
        stat_list = stat_list if isinstance(stat_list, Mapping) else {}
        for stat in _require_list(stat_list.get("stat", []), "stat"):
            stat = _require_object(stat, "a stat")
            key = stat.get("statKey")
            timestamps = stat.get("timestamps")
            data = stat.get("data")
            timestamps = list(timestamps) if isinstance(timestamps, list) else []
            data = list(data) if isinstance(data, list) else []
            interval = stat.get("intervalUnit")
            interval = interval if isinstance(interval, Mapping) else {}
            samples += min(len(timestamps), len(data))
            series.append(
                {
                    "resource_id": entry.get("resourceId"),
                    "stat_key": key.get("key") if isinstance(key, Mapping) else None,
                    "roll_up_type": stat.get("rollUpType"),
                    "interval_type": interval.get("intervalType"),
                    "interval_quantifier": interval.get("quantifier"),
                    "timestamps_ms": timestamps,
                    "values": data,
                }
            )
    return {
        "series": series,
        "series_count": len(series),
        "sample_count": samples,
        "projection_version": STATS_PROJECTION_VERSION,
    }
