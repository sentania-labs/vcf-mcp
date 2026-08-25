"""Report adapters: definition listing and definition detail only.

SPEC section 6. Record 007 classifies a report run as a mutation, so Phase 1
ships no run path. Completed-report listing and download are deferred to Phase
2, where they land alongside the run path that makes them demonstrable:
``GET /api/reports`` on DEVEL returns ``totalCount: 0``, re-verified
2026-07-25, so there is nothing for a listing or a download to operate on.

That reduction against SPEC 4.1's ``reports: list/run/download`` line is
flagged to the principal on issue #2 rather than taken as a team decision.
``GET /api/reportdefinitions`` returns 74 definitions, so this family is not
empty, it is just narrower than the original line.
"""

from __future__ import annotations

from vcf_mcp.contracts import Capability, HttpMethod, JsonObject, OutboundContract
from vcf_mcp.vcf import projection
from vcf_mcp.vcf.adapters.base import ReadAdapter
from vcf_mcp.vcf.caps import clamp_page_size
from vcf_mcp.vcf.client import VcfTargetClient
from vcf_mcp.vcf.outbound import ReadContract


REPORT_DEFINITIONS = ReadContract(
    name="reports.definitions",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/reportdefinitions",
        permitted_query_parameters=frozenset({"page", "pageSize"}),
    ),
    projection_version=projection.REPORT_DEFINITION_PROJECTION_VERSION,
)

REPORT_DEFINITION_DETAIL = ReadContract(
    name="reports.definition_detail",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/reportdefinitions/{report_definition_id}",
        permitted_query_parameters=frozenset(),
    ),
    projection_version=projection.REPORT_DEFINITION_PROJECTION_VERSION,
)


async def list_report_definitions(
    client: VcfTargetClient, *, page: int = 0, page_size: int | None = None
) -> JsonObject:
    size = clamp_page_size(page_size)
    body = await client.request_read(
        REPORT_DEFINITIONS, query={"page": page, "pageSize": size}
    )
    return projection.collection(
        body,
        envelope_key="reportDefinitions",
        projector=projection.report_definition,
        projection_version=REPORT_DEFINITIONS.projection_version,
        requested_page=page,
        requested_page_size=size,
    )


async def get_report_definition(
    client: VcfTargetClient, *, report_definition_id: str
) -> JsonObject:
    body = await client.request_read(
        REPORT_DEFINITION_DETAIL,
        path_parameters={"report_definition_id": report_definition_id},
    )
    return {
        "report_definition": projection.report_definition(body),
        "projection_version": REPORT_DEFINITION_DETAIL.projection_version,
    }


ADAPTERS: tuple[ReadAdapter, ...] = (
    ReadAdapter(
        tool_name="list_report_definitions",
        capability=Capability.READ_REPORTS,
        read_contract=REPORT_DEFINITIONS,
        handler=list_report_definitions,
        summary="List the report definitions available on this target.",
    ),
    ReadAdapter(
        tool_name="get_report_definition",
        capability=Capability.READ_REPORTS,
        read_contract=REPORT_DEFINITION_DETAIL,
        handler=get_report_definition,
        summary="Fetch one report definition by id.",
    ),
)
