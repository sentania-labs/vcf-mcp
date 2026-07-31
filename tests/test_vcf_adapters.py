"""Contract tests for the read adapters, the outbound allowlist, and the caps.

Per SPEC section 11 these assert shape, required-field presence, and monotonic
properties. They never assert an exact object count: the DEVEL inventory moved
from 4 to 517 objects inside one round, and a count assertion would have broken
on a change that was not a defect.

The synthetic responses here are shape-faithful to what was measured against
DEVEL on 2026-07-25, including the envelope key inconsistencies (``adapter-kind``,
``resource-kind``, ``symptom`` singular, ``stat-key``).
"""

from __future__ import annotations

import asyncio
import unittest

import httpx

from vcf_ops_mcp.contracts import (
    REQUIRED_REGISTRATION_CORE,
    Capability,
    ConfigurationGeneration,
    HttpMethod,
    OutboundContract,
    TargetId,
    TargetPosture,
    TargetRecord,
)
from vcf_ops_mcp.vcf.adapters import READ_ADAPTERS, READ_ALLOWLIST, alerts, inventory
from vcf_ops_mcp.vcf.adapters import metrics as metrics_adapters
from vcf_ops_mcp.vcf.adapters import reports as reports_adapters
from vcf_ops_mcp.vcf.caps import (
    MAX_METRICS_RESOURCES,
    MAX_METRICS_STAT_KEYS,
    MAX_PAGE_SIZE,
    METRICS_CELL_CAP,
    clamp_page_size,
    samples_in_window,
)
from vcf_ops_mcp.vcf.client import TargetCredentials, VcfTargetClient
from vcf_ops_mcp.vcf.errors import OutboundContractViolation, ResultCapExceeded
from vcf_ops_mcp.vcf.outbound import OutboundAllowlist, ReadContract, render_path


FAR_FUTURE_MS = 4_102_444_800_000
MINUTE_MS = 60_000


def links(count: int = 3) -> list[dict[str, str]]:
    return [
        {"href": f"/suite-api/api/thing/{index}", "rel": "SELF", "name": "link"}
        for index in range(count)
    ]


def page_info(total: int, page: int = 0, page_size: int = 50) -> dict[str, int]:
    return {"totalCount": total, "page": page, "pageSize": page_size}


RESOURCE_ITEM = {
    "identifier": "11111111-1111-4111-8111-111111111111",
    "creationTime": 1_700_000_000_000,
    "resourceKey": {
        "name": "synthetic-vm-01",
        "adapterKindKey": "VMWARE",
        "resourceKindKey": "VirtualMachine",
        "resourceIdentifiers": [
            {
                "identifierType": {"name": "VMEntityObjectID", "isPartOfUniqueness": True},
                "value": "vm-101",
            }
        ],
    },
    "resourceStatusStates": [
        {
            "adapterInstanceId": "22222222-2222-4222-8222-222222222222",
            "resourceStatus": "DATA_RECEIVING",
            "resourceState": "STARTED",
            "statusMessage": "",
        }
    ],
    "resourceHealth": "GREEN",
    "resourceHealthValue": 100.0,
    "dtEnabled": True,
    "badges": [{"type": "RISK", "color": "GREEN", "score": 0.0}],
    "relatedResources": [],
    "links": links(9),
}

ALERT_ITEM = {
    "alertId": "33333333-3333-4333-8333-333333333333",
    "resourceId": RESOURCE_ITEM["identifier"],
    "alertLevel": "CRITICAL",
    "type": "17",
    "subType": "19",
    "status": "ACTIVE",
    "startTimeUTC": 1_700_000_000_000,
    "cancelTimeUTC": 0,
    "updateTimeUTC": 1_700_000_600_000,
    "suspendUntilTimeUTC": 0,
    "controlState": "OPEN",
    "alertDefinitionId": "AlertDefinition-VMWARE-synthetic",
    "alertDefinitionName": "Synthetic alert definition",
    "alertImpact": "HEALTH",
    "links": links(4),
}

SYMPTOM_ITEM = {
    "id": "44444444-4444-4444-8444-444444444444",
    "resourceId": RESOURCE_ITEM["identifier"],
    "startTimeUTC": 1_700_000_000_000,
    "updateTimeUTC": 1_700_000_600_000,
    "cancelTimeUTC": 0,
    "kpi": False,
    "symptomCriticality": "WARNING",
    "symptomDefinitionId": "SymptomDefinition-VMWARE-synthetic",
    "statKey": "cpu|demandmhz",
    "message": "synthetic symptom",
    "links": links(3),
    "faultDevices": [],
}

STAT_BLOCK = {
    "values": [
        {
            "resourceId": RESOURCE_ITEM["identifier"],
            "stat-list": {
                "stat": [
                    {
                        "timestamps": [1_700_000_000_000, 1_700_000_300_000],
                        "statKey": {"key": "cpu|demandmhz"},
                        "rollUpType": "AVG",
                        "intervalUnit": {"quantifier": 5, "intervalType": "MINUTES"},
                        "data": [12.5, 13.0],
                    }
                ]
            },
        }
    ]
}

RESPONSES: dict[tuple[str, str], dict] = {
    ("GET", "/api/adapterkinds"): {
        "adapter-kind": [
            {
                "key": "VMWARE",
                "name": "VMware vSphere",
                "description": "synthetic",
                "adapterKindType": "GENERAL",
                "describeVersion": 1,
                "identifiers": [],
                "resourceKinds": ["VirtualMachine", "HostSystem"],
                "links": links(2),
            }
        ]
    },
    ("GET", "/api/adapterkinds/VMWARE/resourcekinds"): {
        "pageInfo": page_info(2),
        "links": links(),
        "resource-kind": [
            {
                "key": "VirtualMachine",
                "name": "Virtual Machine",
                "adapterKind": "VMWARE",
                "adapterKindName": "VMware vSphere",
                "resourceKindType": "GENERAL",
                "resourceIdentifierTypes": [],
                "links": links(2),
            }
        ],
    },
    ("GET", "/api/resources"): {
        "pageInfo": page_info(517),
        "links": links(4),
        "resourceList": [RESOURCE_ITEM],
    },
    ("GET", f"/api/resources/{RESOURCE_ITEM['identifier']}"): RESOURCE_ITEM,
    ("GET", f"/api/resources/{RESOURCE_ITEM['identifier']}/statkeys"): {
        "stat-key": [{"key": "cpu|demandmhz"}, {"key": "mem|nonzero_active"}]
    },
    ("GET", "/api/resources/stats/latest"): STAT_BLOCK,
    ("POST", "/api/resources/stats/query"): STAT_BLOCK,
    ("GET", "/api/supermetrics"): {
        "pageInfo": page_info(68),
        "links": links(4),
        "superMetrics": [
            {
                "id": "55555555-5555-4555-8555-555555555555",
                "name": "synthetic super metric",
                "formula": "avg(${this, metric=cpu|demandmhz})",
                "description": "synthetic",
                "modificationTime": 1_700_000_000_000,
            }
        ],
    },
    ("GET", "/api/supermetrics/55555555-5555-4555-8555-555555555555"): {
        "id": "55555555-5555-4555-8555-555555555555",
        "name": "synthetic super metric",
        "formula": "avg(${this, metric=cpu|demandmhz})",
        "description": "synthetic",
        "modificationTime": 1_700_000_000_000,
    },
    ("POST", "/api/alerts/query"): {
        "pageInfo": page_info(1216),
        "links": links(4),
        "alerts": [ALERT_ITEM],
    },
    ("GET", "/api/alerts"): {
        "pageInfo": page_info(15),
        "links": links(4),
        "alerts": [ALERT_ITEM],
    },
    ("GET", f"/api/alerts/{ALERT_ITEM['alertId']}"): ALERT_ITEM,
    ("GET", "/api/alertdefinitions"): {
        "pageInfo": page_info(320),
        "links": links(4),
        "alertDefinitions": [
            {
                "id": "AlertDefinition-VMWARE-synthetic",
                "name": "Synthetic alert definition",
                "description": "synthetic",
                "adapterKindKey": "VMWARE",
                "resourceKindKey": "VirtualMachine",
                "waitCycles": 1,
                "cancelCycles": 1,
                "type": 17,
                "subType": 19,
                "states": [],
                "forVCDTenants": False,
            }
        ],
    },
    ("GET", "/api/alertdefinitions/AlertDefinition-VMWARE-synthetic"): {
        "id": "AlertDefinition-VMWARE-synthetic",
        "name": "Synthetic alert definition",
        "description": "synthetic",
        "adapterKindKey": "VMWARE",
        "resourceKindKey": "VirtualMachine",
        "waitCycles": 1,
        "cancelCycles": 1,
    },
    ("GET", "/api/symptoms"): {
        "pageInfo": page_info(8),
        "links": links(4),
        "symptom": [SYMPTOM_ITEM],
    },
    ("GET", "/api/symptomdefinitions"): {
        "pageInfo": page_info(1846),
        "links": links(4),
        "symptomDefinitions": [
            {
                "id": "SymptomDefinition-VMWARE-synthetic",
                "name": "Synthetic symptom definition",
                "adapterKindKey": "VMWARE",
                "resourceKindKey": "VirtualMachine",
                "state": {"severity": "WARNING"},
                "waitCycles": 1,
                "cancelCycles": 1,
            }
        ],
    },
    ("GET", "/api/symptomdefinitions/SymptomDefinition-VMWARE-synthetic"): {
        "id": "SymptomDefinition-VMWARE-synthetic",
        "name": "Synthetic symptom definition",
        "adapterKindKey": "VMWARE",
        "resourceKindKey": "VirtualMachine",
        "state": {"severity": "WARNING"},
        "waitCycles": 1,
        "cancelCycles": 1,
    },
    ("GET", "/api/reportdefinitions"): {
        "pageInfo": page_info(74),
        "links": links(4),
        "reportDefinitions": [
            {
                "id": "66666666-6666-4666-8666-666666666666",
                "name": "Synthetic report definition",
                "description": "synthetic",
                "subject": ["VirtualMachine"],
                "owner": "admin",
                "active": True,
                "traversal-specs": [],
            }
        ],
    },
    ("GET", "/api/reportdefinitions/66666666-6666-4666-8666-666666666666"): {
        "id": "66666666-6666-4666-8666-666666666666",
        "name": "Synthetic report definition",
        "description": "synthetic",
        "subject": ["VirtualMachine"],
        "owner": "admin",
        "active": True,
    },
}


class RecordingAppliance:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/suite-api")
        if path.endswith("/token/acquire"):
            return httpx.Response(
                200, json={"token": "tok-1", "validity": FAR_FUTURE_MS, "roles": []}
            )
        if path.endswith("/token/release"):
            return httpx.Response(200, json={})
        self.calls.append(request)
        payload = RESPONSES.get((request.method, path))
        if payload is None:  # pragma: no cover, a missing fixture is a test bug
            raise AssertionError(f"no synthetic response for {request.method} {path}")
        return httpx.Response(200, json=payload)


def build_client() -> tuple[VcfTargetClient, RecordingAppliance]:
    appliance = RecordingAppliance()
    record = TargetRecord(
        id=TargetId("t-1"),
        name="devel",
        fqdn="vcf-ops-devel.invalid",
        posture=TargetPosture.READ_ONLY,
        is_prod=False,
        verify_ssl=False,
        auth_source="LOCAL",
        configuration_generation=ConfigurationGeneration(1),
    )
    client = VcfTargetClient(
        target=record,
        credentials=TargetCredentials("svc-reader", "synthetic", "LOCAL"),
        allowlist=READ_ALLOWLIST,
        http_client=httpx.AsyncClient(
            base_url=f"https://{record.fqdn}/suite-api",
            transport=httpx.MockTransport(appliance),
        ),
    )
    return client, appliance


def contains_links(value: object) -> bool:
    if isinstance(value, dict):
        return "links" in value or any(contains_links(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_links(item) for item in value)
    return False


class AdapterDeclarationTests(unittest.TestCase):
    """The pinned criterion: every adapter declares its full outbound triple."""

    def test_every_adapter_declares_method_path_parameters_and_projection(self) -> None:
        self.assertTrue(READ_ADAPTERS)
        for adapter in READ_ADAPTERS:
            with self.subTest(tool=adapter.tool_name):
                contract = adapter.read_contract.contract
                self.assertIsInstance(contract, OutboundContract)
                self.assertIn(contract.method, (HttpMethod.GET, HttpMethod.POST))
                self.assertTrue(contract.path_template.startswith("/api/"))
                self.assertIsInstance(
                    contract.permitted_query_parameters, frozenset
                )
                self.assertTrue(adapter.projection_version)
                self.assertRegex(adapter.projection_version, r"^[a-z_]+\.v\d+$")

    def test_registration_mapping_fills_the_required_core(self) -> None:
        async def audited(**_: object) -> dict[str, object]:
            return {}

        for adapter in READ_ADAPTERS:
            with self.subTest(tool=adapter.tool_name):
                mapping = adapter.registration_mapping(audited_handler=audited)
                self.assertTrue(REQUIRED_REGISTRATION_CORE.issubset(mapping))
                self.assertEqual(mapping["schema_version"], 1)
                self.assertEqual(mapping["capability"], mapping["key_scope"])
                # Family-qualified extensions, never new core keys.
                extras = (
                    set(mapping)
                    - REQUIRED_REGISTRATION_CORE
                    - {"adapter.summary"}
                )
                self.assertTrue(all(key.startswith("vcf.") for key in extras), extras)

    def test_tool_names_and_contract_names_are_unique(self) -> None:
        tool_names = [adapter.tool_name for adapter in READ_ADAPTERS]
        contract_names = [adapter.read_contract.name for adapter in READ_ADAPTERS]
        self.assertEqual(len(tool_names), len(set(tool_names)))
        self.assertEqual(len(contract_names), len(set(contract_names)))

    def test_every_capability_is_a_read_capability(self) -> None:
        read_capabilities = {
            Capability.READ_INVENTORY,
            Capability.READ_METRICS,
            Capability.READ_ALERTS,
            Capability.READ_REPORTS,
        }
        for adapter in READ_ADAPTERS:
            self.assertIn(adapter.capability, read_capabilities)

    def test_body_keys_only_appear_on_post_contracts(self) -> None:
        for adapter in READ_ADAPTERS:
            if adapter.read_contract.permitted_body_keys:
                self.assertIs(
                    adapter.read_contract.contract.method, HttpMethod.POST
                )

    def test_max_samples_is_not_a_permitted_body_key(self) -> None:
        """It is ignored by the appliance, so sending it would be a false bound."""

        self.assertNotIn(
            "maxSamples", metrics_adapters.RANGED_STATS.permitted_body_keys
        )


class OutboundAllowlistTests(unittest.TestCase):
    def test_unknown_query_parameter_is_refused_before_any_request(self) -> None:
        with self.assertRaises(OutboundContractViolation) as caught:
            asyncio.run(self._search(identifier="anything"))
        self.assertIn("identifier", str(caught.exception))

    async def _search(self, **query: object) -> object:
        client, _ = build_client()
        try:
            return await client.request_read(
                inventory.SEARCH_RESOURCES, query=query
            )
        finally:
            await client.aclose(release_token=False)

    def test_path_parameter_cannot_leave_its_segment(self) -> None:
        for hostile in ("../alerts", "a/b", "with space", "", "%2e%2e"):
            with self.subTest(value=hostile):
                with self.assertRaises(OutboundContractViolation):
                    render_path(
                        inventory.RESOURCE_DETAIL, {"resource_id": hostile}
                    )

    def test_missing_or_extra_path_parameters_are_refused(self) -> None:
        with self.assertRaises(OutboundContractViolation):
            render_path(inventory.RESOURCE_DETAIL, {})
        with self.assertRaises(OutboundContractViolation):
            render_path(
                inventory.RESOURCE_DETAIL,
                {"resource_id": "abc", "extra": "def"},
            )

    def test_a_contract_outside_the_frozen_allowlist_is_refused(self) -> None:
        rogue = ReadContract(
            name="rogue.tool",
            contract=OutboundContract(
                method=HttpMethod.POST,
                path_template="/api/actions/run",
                permitted_query_parameters=frozenset(),
            ),
            projection_version="rogue.v1",
        )

        async def attempt() -> None:
            client, appliance = build_client()
            try:
                with self.assertRaises(OutboundContractViolation):
                    await client.request_read(rogue)
                self.assertEqual(appliance.calls, [])
            finally:
                await client.aclose(release_token=False)

        asyncio.run(attempt())

    def test_a_body_key_outside_the_allowlist_is_refused(self) -> None:
        async def attempt() -> None:
            client, _ = build_client()
            try:
                with self.assertRaises(OutboundContractViolation):
                    await client.request_read(
                        alerts.SEARCH_ALERTS, body={"resourceId": ["anything"]}
                    )
            finally:
                await client.aclose(release_token=False)

        asyncio.run(attempt())

    def test_a_body_cannot_be_sent_on_a_get_contract(self) -> None:
        async def attempt() -> None:
            client, _ = build_client()
            try:
                with self.assertRaises(OutboundContractViolation):
                    await client.request_read(
                        inventory.SEARCH_RESOURCES, body={"name": "x"}
                    )
            finally:
                await client.aclose(release_token=False)

        asyncio.run(attempt())

    def test_frozen_pairs_cover_every_adapter_and_nothing_else(self) -> None:
        declared = {
            (a.read_contract.contract.method, a.read_contract.contract.path_template)
            for a in READ_ADAPTERS
        }
        self.assertEqual(READ_ALLOWLIST.frozen_pairs, declared)

    def test_duplicate_contract_names_are_refused_at_freeze_time(self) -> None:
        contract = inventory.SEARCH_RESOURCES
        with self.assertRaises(ValueError):
            OutboundAllowlist([contract, contract])


class AdapterShapeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client, self.appliance = build_client()

    async def asyncTearDown(self) -> None:
        await self.client.aclose(release_token=False)

    def assert_request_matched_contract(self, contract: ReadContract) -> None:
        request = self.appliance.calls[-1]
        self.assertEqual(request.method, str(contract.contract.method))
        supplied = set(request.url.params.keys())
        self.assertTrue(
            supplied.issubset(contract.contract.permitted_query_parameters),
            f"{supplied} escaped {contract.contract.permitted_query_parameters}",
        )

    async def test_search_resources_projects_and_drops_links(self) -> None:
        result = await inventory.search_resources(
            self.client, resource_kind="VirtualMachine", page_size=10
        )
        self.assert_request_matched_contract(inventory.SEARCH_RESOURCES)
        self.assertFalse(contains_links(result))
        self.assertEqual(result["projection_version"], "resource.v1")
        # Monotonic properties, never an exact object count.
        self.assertLessEqual(len(result["items"]), result["page_size"])
        self.assertGreaterEqual(result["total_count"], len(result["items"]))
        self.assertTrue(result["has_more"])
        for item in result["items"]:
            self.assertTrue(item["id"])
            self.assertTrue(item["name"])
            self.assertTrue(item["resource_kind"])

    async def test_paging_metadata_is_computed_not_read_from_links(self) -> None:
        """A NEXT link is present even on a single page, so has_more is computed."""

        result = await alerts.list_resource_alerts(
            self.client, resource_id=RESOURCE_ITEM["identifier"], page_size=50
        )
        self.assertFalse(result["has_more"])  # 15 total, page 0, size 50
        self.assertFalse(contains_links(result))

    async def test_resource_detail_projects_one_object(self) -> None:
        result = await inventory.get_resource(
            self.client, resource_id=RESOURCE_ITEM["identifier"]
        )
        self.assertEqual(result["resource"]["id"], RESOURCE_ITEM["identifier"])
        self.assertFalse(contains_links(result))

    async def test_adapter_and_resource_kind_envelopes(self) -> None:
        kinds = await inventory.list_adapter_kinds(self.client)
        self.assertTrue(all(item["key"] for item in kinds["items"]))
        resource_kinds = await inventory.list_resource_kinds(
            self.client, adapter_kind_key="VMWARE"
        )
        self.assertTrue(all(item["key"] for item in resource_kinds["items"]))

    async def test_stat_key_discovery_and_stats_projection(self) -> None:
        keys = await metrics_adapters.discover_stat_keys(
            self.client, resource_id=RESOURCE_ITEM["identifier"]
        )
        self.assertTrue(all(item["stat_key"] for item in keys["items"]))

        latest = await metrics_adapters.get_latest_stats(
            self.client,
            resource_ids=[RESOURCE_ITEM["identifier"]],
            stat_keys=["cpu|demandmhz"],
        )
        self.assert_request_matched_contract(metrics_adapters.LATEST_STATS)
        self.assertEqual(latest["projection_version"], "stats.v1")
        for series in latest["series"]:
            self.assertEqual(len(series["timestamps_ms"]), len(series["values"]))
            self.assertTrue(series["stat_key"])

    async def test_ranged_stats_sends_only_permitted_body_keys(self) -> None:
        end = 1_700_003_600_000
        result = await metrics_adapters.get_ranged_stats(
            self.client,
            resource_ids=[RESOURCE_ITEM["identifier"]],
            stat_keys=["cpu|demandmhz"],
            begin_ms=end - 3_600_000,
            end_ms=end,
        )
        request = self.appliance.calls[-1]
        self.assertEqual(request.method, "POST")
        import json

        sent = json.loads(request.content)
        self.assertTrue(
            set(sent).issubset(metrics_adapters.RANGED_STATS.permitted_body_keys)
        )
        self.assertNotIn("maxSamples", sent)
        self.assertEqual(result["requested_samples_per_series"], 13)

    async def test_alert_search_filters_travel_in_the_body(self) -> None:
        await alerts.search_alerts(
            self.client, active_only=True, criticalities=["CRITICAL"]
        )
        request = self.appliance.calls[-1]
        import json

        sent = json.loads(request.content)
        self.assertEqual(sent["activeOnly"], True)
        self.assertEqual(sent["alertCriticality"], ["CRITICAL"])
        self.assertNotIn("resourceId", sent)

    async def test_alert_and_symptom_projections(self) -> None:
        alert = await alerts.get_alert(self.client, alert_id=ALERT_ITEM["alertId"])
        self.assertEqual(alert["alert"]["id"], ALERT_ITEM["alertId"])
        self.assertFalse(contains_links(alert))

        symptoms = await alerts.list_resource_symptoms(
            self.client, resource_id=RESOURCE_ITEM["identifier"]
        )
        self.assertTrue(all(item["id"] for item in symptoms["items"]))
        self.assertFalse(contains_links(symptoms))

        definitions = await alerts.list_symptom_definitions(self.client)
        self.assertTrue(all(item["id"] for item in definitions["items"]))
        detail = await alerts.get_symptom_definition(
            self.client, symptom_definition_id="SymptomDefinition-VMWARE-synthetic"
        )
        self.assertTrue(detail["symptom_definition"]["name"])

    async def test_alert_definition_listing_and_detail(self) -> None:
        listing = await alerts.list_alert_definitions(self.client)
        self.assertTrue(all(item["id"] for item in listing["items"]))
        detail = await alerts.get_alert_definition(
            self.client, alert_definition_id="AlertDefinition-VMWARE-synthetic"
        )
        self.assertTrue(detail["alert_definition"]["name"])

    async def test_super_metric_listing_and_detail(self) -> None:
        listing = await metrics_adapters.list_super_metrics(self.client)
        self.assertTrue(all(item["formula"] for item in listing["items"]))
        detail = await metrics_adapters.get_super_metric(
            self.client, super_metric_id="55555555-5555-4555-8555-555555555555"
        )
        self.assertTrue(detail["super_metric"]["formula"])

    async def test_report_definitions_listing_and_detail(self) -> None:
        listing = await reports_adapters.list_report_definitions(self.client)
        self.assertTrue(all(item["id"] for item in listing["items"]))
        detail = await reports_adapters.get_report_definition(
            self.client, report_definition_id="66666666-6666-4666-8666-666666666666"
        )
        self.assertTrue(detail["report_definition"]["name"])

    async def test_page_size_is_clamped_to_the_server_maximum(self) -> None:
        await inventory.search_resources(self.client, page_size=10_000)
        request = self.appliance.calls[-1]
        self.assertEqual(request.url.params["pageSize"], str(MAX_PAGE_SIZE))


class MetricsCapTests(unittest.IsolatedAsyncioTestCase):
    """Caps refuse rather than truncate, and the refusal names the cap."""

    async def asyncSetUp(self) -> None:
        self.client, self.appliance = build_client()

    async def asyncTearDown(self) -> None:
        await self.client.aclose(release_token=False)

    async def test_too_many_resources_is_refused_before_the_request(self) -> None:
        with self.assertRaises(ResultCapExceeded) as caught:
            await metrics_adapters.get_latest_stats(
                self.client,
                resource_ids=[f"id-{index}" for index in range(MAX_METRICS_RESOURCES + 1)],
                stat_keys=["cpu|demandmhz"],
            )
        self.assertEqual(caught.exception.cap_name, "MAX_METRICS_RESOURCES")
        self.assertIn("MAX_METRICS_RESOURCES", str(caught.exception))
        self.assertIn(str(MAX_METRICS_RESOURCES), str(caught.exception))
        self.assertEqual(self.appliance.calls, [])

    async def test_too_many_stat_keys_is_refused(self) -> None:
        with self.assertRaises(ResultCapExceeded) as caught:
            await metrics_adapters.get_latest_stats(
                self.client,
                resource_ids=["id-0"],
                stat_keys=[f"key-{index}" for index in range(MAX_METRICS_STAT_KEYS + 1)],
            )
        self.assertEqual(caught.exception.cap_name, "MAX_METRICS_STAT_KEYS")
        self.assertEqual(self.appliance.calls, [])

    async def test_cell_product_over_the_cap_is_refused_with_both_numbers(self) -> None:
        end = 1_700_000_000_000
        begin = end - 400 * MINUTE_MS  # 81 samples at a 5 minute interval
        with self.assertRaises(ResultCapExceeded) as caught:
            await metrics_adapters.get_ranged_stats(
                self.client,
                resource_ids=[f"id-{index}" for index in range(40)],
                stat_keys=[f"key-{index}" for index in range(20)],
                begin_ms=begin,
                end_ms=end,
            )
        message = str(caught.exception)
        self.assertEqual(caught.exception.cap_name, "METRICS_CELL_CAP")
        self.assertIn(str(METRICS_CELL_CAP), message)
        self.assertIn(str(caught.exception.requested), message)
        self.assertIn("refuses rather than returning a truncated series", message)
        self.assertEqual(self.appliance.calls, [])

    async def test_a_request_at_the_cap_is_allowed(self) -> None:
        end = 1_700_000_000_000
        begin = end - 45 * MINUTE_MS  # 10 samples at a 5 minute interval
        result = await metrics_adapters.get_ranged_stats(
            self.client,
            resource_ids=[RESOURCE_ITEM["identifier"]],
            stat_keys=["cpu|demandmhz"],
            begin_ms=begin,
            end_ms=end,
        )
        self.assertEqual(result["requested_cells"], 10)
        self.assertEqual(len(self.appliance.calls), 1)


class CapArithmeticTests(unittest.TestCase):
    def test_sample_count_follows_the_window_not_a_request_field(self) -> None:
        end = 1_700_000_000_000
        self.assertEqual(
            samples_in_window(
                begin_ms=end - 3_600_000,
                end_ms=end,
                interval_type="MINUTES",
                quantifier=5,
            ),
            13,
        )
        self.assertEqual(
            samples_in_window(
                begin_ms=end - 86_400_000,
                end_ms=end,
                interval_type="HOURS",
                quantifier=1,
            ),
            25,
        )

    def test_a_window_that_does_not_advance_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            samples_in_window(
                begin_ms=10, end_ms=10, interval_type="MINUTES", quantifier=5
            )

    def test_an_unsupported_interval_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            samples_in_window(
                begin_ms=0, end_ms=10_000, interval_type="FORTNIGHTS", quantifier=1
            )

    def test_page_size_clamping_is_monotonic(self) -> None:
        self.assertEqual(clamp_page_size(None), clamp_page_size(None))
        self.assertLessEqual(clamp_page_size(10_000), MAX_PAGE_SIZE)
        self.assertEqual(clamp_page_size(0), 1)
        self.assertLessEqual(clamp_page_size(25), clamp_page_size(75))


if __name__ == "__main__":
    unittest.main()
