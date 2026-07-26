"""Inventory adapters: adapter kinds, resource kinds, resource search, detail.

Query parameters here are the ones measured to actually filter on DEVEL:
``resourceKind`` (517 to 49), ``adapterKind`` (517 to 169), and ``name`` (517
to 0 for a name that does not exist). Anything not in a contract's allowlist is
refused before the request is built, because this appliance answers an
unrecognized parameter with the whole unfiltered collection and a 200.
"""

from __future__ import annotations

from vcf_ops_mcp.contracts import Capability, HttpMethod, JsonObject, OutboundContract
from vcf_ops_mcp.vcf import projection
from vcf_ops_mcp.vcf.adapters.base import ReadAdapter
from vcf_ops_mcp.vcf.caps import clamp_page_size
from vcf_ops_mcp.vcf.client import VcfTargetClient
from vcf_ops_mcp.vcf.outbound import ReadContract


ADAPTER_KINDS = ReadContract(
    name="inventory.adapter_kinds",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/adapterkinds",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.ADAPTER_KIND_PROJECTION_VERSION,
)

RESOURCE_KINDS = ReadContract(
    name="inventory.resource_kinds",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/adapterkinds/{adapter_kind_key}/resourcekinds",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.RESOURCE_KIND_PROJECTION_VERSION,
)

SEARCH_RESOURCES = ReadContract(
    name="inventory.search_resources",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/resources",
        permitted_query_parameters=frozenset(
            {"name", "adapterKind", "resourceKind", "page", "pageSize"}
        ),
    ),
    projection_version=projection.RESOURCE_PROJECTION_VERSION,
)

RESOURCE_DETAIL = ReadContract(
    name="inventory.resource_detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/resources/{resource_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.RESOURCE_PROJECTION_VERSION,
)


async def list_adapter_kinds(client: VcfTargetClient) -> JsonObject:
    body = await client.request_read(ADAPTER_KINDS)
    return projection.collection(
        body,
        envelope_key="adapter-kind",
        projector=projection.adapter_kind,
        projection_version=ADAPTER_KINDS.projection_version,
    )


async def list_resource_kinds(
    client: VcfTargetClient,
    *,
    adapter_kind_key: str,
    page: int = 0,
    page_size: int | None = None,
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        RESOURCE_KINDS,
        path_parameters={"adapter_kind_key": adapter_kind_key},
        query={"page": page, "pageSize": size},
    )
    return projection.collection(
        body,
        envelope_key="resource-kind",
        projector=projection.resource_kind,
        projection_version=RESOURCE_KINDS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def search_resources(
    client: VcfTargetClient,
    *,
    name: str | None = None,
    adapter_kind: str | None = None,
    resource_kind: str | None = None,
    page: int = 0,
    page_size: int | None = None,
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        SEARCH_RESOURCES,
        query={
            "name": name,
            "adapterKind": adapter_kind,
            "resourceKind": resource_kind,
            "page": page,
            "pageSize": size,
        },
    )
    return projection.collection(
        body,
        envelope_key="resourceList",
        projector=projection.resource,
        projection_version=SEARCH_RESOURCES.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_resource(client: VcfTargetClient, *, resource_id: str) -> JsonObject:
    body = await client.request_read(
        RESOURCE_DETAIL, path_parameters={"resource_id": resource_id}
    )
    return {
        "resource": projection.resource(body),
        "projection_version": RESOURCE_DETAIL.projection_version,
    }


ADAPTERS: tuple[ReadAdapter, ...] = (
    ReadAdapter(
        tool_name="list_adapter_kinds",
        capability=Capability.READ_INVENTORY,
        read_contract=ADAPTER_KINDS,
        handler=list_adapter_kinds,
        summary="List the adapter kinds this target collects from.",
    ),
    ReadAdapter(
        tool_name="list_resource_kinds",
        capability=Capability.READ_INVENTORY,
        read_contract=RESOURCE_KINDS,
        handler=list_resource_kinds,
        summary="List the resource kinds one adapter kind provides.",
    ),
    ReadAdapter(
        tool_name="search_resources",
        capability=Capability.READ_INVENTORY,
        read_contract=SEARCH_RESOURCES,
        handler=search_resources,
        summary="Search inventory by name, adapter kind, or resource kind.",
    ),
    ReadAdapter(
        tool_name="get_resource",
        capability=Capability.READ_INVENTORY,
        read_contract=RESOURCE_DETAIL,
        handler=get_resource,
        summary="Fetch one resource by its stable identifier.",
    ),
)
