"""Alert and symptom adapters. Read-only, per record 008.

There is no acknowledgement verb, no cancel, and no suspend in this family.
None of them is deferred; none of them is here to be enabled later.

The filter surface is asymmetric on this appliance and it was measured on
2026-07-25 rather than reasoned about:

- ``GET /api/alerts?activeOnly=true``, ``?alertCriticality=CRITICAL``, and
  ``?status=ACTIVE`` are silently ignored. Total stays 1216 of 1216.
- The same filters in the body of ``POST /api/alerts/query`` work:
  ``activeOnly`` gives 40, ``alertCriticality: [CRITICAL]`` gives 703,
  ``[WARNING]`` gives 187, and ``alertDefinitionId`` gives 0 for an id no alert
  references.
- ``resourceId`` and ``status`` in that POST body are ignored (1216), while
  ``GET /api/alerts?resourceId=`` does filter (15).

So criticality and active filtering live on the POST adapter, resource
filtering lives on the GET adapter, and neither adapter declares the parameter
that the other endpoint honors. A single merged tool would have to send a
parameter that is silently dropped half the time.

**Live symptom detail does not exist on this API.** ``GET /api/symptoms/{id}``
is a 404, ``GET /api/symptoms?id=`` is silently ignored, and every body filter
tried against ``POST /api/symptoms/query`` (id, resourceId,
symptomDefinitionIds, activeOnly) returned the unfiltered 879. The only
effective filter is ``GET /api/symptoms?resourceId=``. Symptom detail is
therefore served as the symptom *definition* (which does have a working detail
endpoint), plus the per-resource listing. No adapter here pretends to a
lookup-by-symptom-id the appliance cannot do.
"""

from __future__ import annotations

from collections.abc import Sequence

from vcf_ops_mcp.contracts import Capability, HttpMethod, JsonObject, OutboundContract
from vcf_ops_mcp.vcf import projection
from vcf_ops_mcp.vcf.adapters.base import ReadAdapter
from vcf_ops_mcp.vcf.caps import clamp_page_size
from vcf_ops_mcp.vcf.client import VcfTargetClient
from vcf_ops_mcp.vcf.outbound import ReadContract


SEARCH_ALERTS = ReadContract(
    name="alerts.search",
    contract=OutboundContract(
        method=HttpMethod.POST,
        path_template="/api/alerts/query",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.ALERT_PROJECTION_VERSION,
    permitted_body_keys=frozenset(
        {"activeOnly", "alertCriticality", "alertDefinitionId"}
    ),
)

RESOURCE_ALERTS = ReadContract(
    name="alerts.by_resource",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/alerts",
        permitted_query_parameters=frozenset({"resourceId", "page", "pageSize"}),
    ),
    projection_version=projection.ALERT_PROJECTION_VERSION,
)

ALERT_DETAIL = ReadContract(
    name="alerts.detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/alerts/{alert_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.ALERT_PROJECTION_VERSION,
)

ALERT_DEFINITIONS = ReadContract(
    name="alerts.definitions",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/alertdefinitions",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.ALERT_DEFINITION_PROJECTION_VERSION,
)

ALERT_DEFINITION_DETAIL = ReadContract(
    name="alerts.definition_detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/alertdefinitions/{alert_definition_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.ALERT_DEFINITION_PROJECTION_VERSION,
)

RESOURCE_SYMPTOMS = ReadContract(
    name="symptoms.by_resource",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/symptoms",
        permitted_query_parameters=frozenset({"resourceId", "page", "pageSize"}),
    ),
    projection_version=projection.SYMPTOM_PROJECTION_VERSION,
)

SYMPTOM_DEFINITIONS = ReadContract(
    name="symptoms.definitions",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/symptomdefinitions",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.SYMPTOM_DEFINITION_PROJECTION_VERSION,
)

SYMPTOM_DEFINITION_DETAIL = ReadContract(
    name="symptoms.definition_detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/symptomdefinitions/{symptom_definition_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.SYMPTOM_DEFINITION_PROJECTION_VERSION,
)


async def search_alerts(
    client: VcfTargetClient,
    *,
    active_only: bool | None = None,
    criticalities: Sequence[str] | None = None,
    alert_definition_ids: Sequence[str] | None = None,
    page: int = 0,
    page_size: int | None = None,
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        SEARCH_ALERTS,
        query={"page": page, "pageSize": size},
        body={
            "activeOnly": active_only,
            "alertCriticality": list(criticalities) if criticalities else None,
            "alertDefinitionId": list(alert_definition_ids)
            if alert_definition_ids
            else None,
        },
    )
    return projection.collection(
        body,
        envelope_key="alerts",
        projector=projection.alert,
        projection_version=SEARCH_ALERTS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def list_resource_alerts(
    client: VcfTargetClient,
    *,
    resource_id: str,
    page: int = 0,
    page_size: int | None = None,
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        RESOURCE_ALERTS,
        query={"resourceId": resource_id, "page": page, "pageSize": size},
    )
    return projection.collection(
        body,
        envelope_key="alerts",
        projector=projection.alert,
        projection_version=RESOURCE_ALERTS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_alert(client: VcfTargetClient, *, alert_id: str) -> JsonObject:
    body = await client.request_read(
        ALERT_DETAIL, path_parameters={"alert_id": alert_id}
    )
    return {
        "alert": projection.alert(body),
        "projection_version": ALERT_DETAIL.projection_version,
    }


async def list_alert_definitions(
    client: VcfTargetClient, *, page: int = 0, page_size: int | None = None
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        ALERT_DEFINITIONS, query={"page": page, "pageSize": size}
    )
    return projection.collection(
        body,
        envelope_key="alertDefinitions",
        projector=projection.alert_definition,
        projection_version=ALERT_DEFINITIONS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_alert_definition(
    client: VcfTargetClient, *, alert_definition_id: str
) -> JsonObject:
    body = await client.request_read(
        ALERT_DEFINITION_DETAIL,
        path_parameters={"alert_definition_id": alert_definition_id},
    )
    return {
        "alert_definition": projection.alert_definition(body),
        "projection_version": ALERT_DEFINITION_DETAIL.projection_version,
    }


async def list_resource_symptoms(
    client: VcfTargetClient,
    *,
    resource_id: str,
    page: int = 0,
    page_size: int | None = None,
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        RESOURCE_SYMPTOMS,
        query={"resourceId": resource_id, "page": page, "pageSize": size},
    )
    return projection.collection(
        body,
        envelope_key="symptom",
        projector=projection.symptom,
        projection_version=RESOURCE_SYMPTOMS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def list_symptom_definitions(
    client: VcfTargetClient, *, page: int = 0, page_size: int | None = None
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        SYMPTOM_DEFINITIONS, query={"page": page, "pageSize": size}
    )
    return projection.collection(
        body,
        envelope_key="symptomDefinitions",
        projector=projection.symptom_definition,
        projection_version=SYMPTOM_DEFINITIONS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_symptom_definition(
    client: VcfTargetClient, *, symptom_definition_id: str
) -> JsonObject:
    body = await client.request_read(
        SYMPTOM_DEFINITION_DETAIL,
        path_parameters={"symptom_definition_id": symptom_definition_id},
    )
    return {
        "symptom_definition": projection.symptom_definition(body),
        "projection_version": SYMPTOM_DEFINITION_DETAIL.projection_version,
    }


ADAPTERS: tuple[ReadAdapter, ...] = (
    ReadAdapter(
        tool_name="search_alerts",
        capability=Capability.READ_ALERTS,
        read_contract=SEARCH_ALERTS,
        handler=search_alerts,
        summary="Search alerts by active state, criticality, or definition.",
    ),
    ReadAdapter(
        tool_name="list_resource_alerts",
        capability=Capability.READ_ALERTS,
        read_contract=RESOURCE_ALERTS,
        handler=list_resource_alerts,
        summary="List the alerts raised against one resource.",
    ),
    ReadAdapter(
        tool_name="get_alert",
        capability=Capability.READ_ALERTS,
        read_contract=ALERT_DETAIL,
        handler=get_alert,
        summary="Fetch one alert by id.",
    ),
    ReadAdapter(
        tool_name="list_alert_definitions",
        capability=Capability.READ_ALERTS,
        read_contract=ALERT_DEFINITIONS,
        handler=list_alert_definitions,
        summary="List alert definitions configured on this target.",
    ),
    ReadAdapter(
        tool_name="get_alert_definition",
        capability=Capability.READ_ALERTS,
        read_contract=ALERT_DEFINITION_DETAIL,
        handler=get_alert_definition,
        summary="Fetch one alert definition by id.",
    ),
    ReadAdapter(
        tool_name="list_resource_symptoms",
        capability=Capability.READ_ALERTS,
        read_contract=RESOURCE_SYMPTOMS,
        handler=list_resource_symptoms,
        summary="List the symptoms firing on one resource.",
    ),
    ReadAdapter(
        tool_name="list_symptom_definitions",
        capability=Capability.READ_ALERTS,
        read_contract=SYMPTOM_DEFINITIONS,
        handler=list_symptom_definitions,
        summary="List symptom definitions configured on this target.",
    ),
    ReadAdapter(
        tool_name="get_symptom_definition",
        capability=Capability.READ_ALERTS,
        read_contract=SYMPTOM_DEFINITION_DETAIL,
        handler=get_symptom_definition,
        summary="Fetch one symptom definition by id.",
    ),
)
