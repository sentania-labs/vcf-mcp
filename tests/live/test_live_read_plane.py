"""Tier 3: read-only live contract tests against the DEVEL appliance.

Never in CI. Run at every gate and after every appliance upgrade. Everything
here reads. Nothing here mutates, and the transport refuses a request outside
the enumerated read set before it is sent.

Assertions are shape, required-field presence, and monotonic properties. No
test asserts an exact object count: the DEVEL inventory moved from 4 to 517
inside one round, and a count assertion would have failed on a change that was
not a defect.

The section 4.2 assertion below is the required one. It is the only control in
this project that no fixture can validate, because a mock answers whatever URL
it is handed.
"""

from __future__ import annotations

import httpx
import pytest

from tests.live.guard import OutsideTheReadSet, refuse_outside_the_read_set
from vcf_ops_mcp.vcf.adapters import alerts, inventory
from vcf_ops_mcp.vcf.adapters import metrics as metrics_adapters
from vcf_ops_mcp.vcf.adapters import reports as reports_adapters
from vcf_ops_mcp.vcf.caps import MAX_METRICS_RESOURCES, samples_in_window
from vcf_ops_mcp.vcf.client import SUITE_API_ROOT, TOKEN_ACQUIRE_PATH
from vcf_ops_mcp.vcf.errors import OutboundContractViolation, ResultCapExceeded


pytestmark = pytest.mark.live

MINUTE_MS = 60_000


def raw_client(target) -> httpx.AsyncClient:
    """A hooked client for the two checks that must bypass request_read."""

    return httpx.AsyncClient(
        base_url=f"https://{target.fqdn}{SUITE_API_ROOT}",
        verify=target.verify_ssl,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        event_hooks={"request": [refuse_outside_the_read_set]},
    )


async def raw_token(client: httpx.AsyncClient, credentials) -> str:
    response = await client.post(
        TOKEN_ACQUIRE_PATH,
        json=credentials.acquire_payload(),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    return response.json()["token"]


class TestAuthentication:
    def test_acquire_returns_an_absolute_expiry_and_unusable_roles(
        self, live, live_credentials
    ) -> None:
        async def acquire() -> dict:
            client = raw_client(live.client._target)  # noqa: SLF001
            try:
                response = await client.post(
                    TOKEN_ACQUIRE_PATH,
                    json=live_credentials.acquire_payload(),
                    headers={"Accept": "application/json"},
                )
                assert response.status_code == 200
                return response.json()
            finally:
                await client.aclose()

        body = live.run(acquire())
        assert set(body) >= {"token", "validity", "expiresAt", "roles"}
        assert isinstance(body["validity"], int)
        # An absolute epoch in milliseconds, not a duration. A duration would
        # be a small number; this is a timestamp past 2020.
        assert body["validity"] > 1_600_000_000_000
        # Always empty, and therefore never usable for authorization.
        assert body["roles"] == []


class TestParameterAllowlist:
    """SPEC 4.2's required live assertion.

    Every permitted query parameter must have an observable effect, and an
    unrecognized one must be shown to be silently ignored. That second half is
    why the allowlist exists at all.
    """

    def test_every_permitted_inventory_filter_has_an_observable_effect(
        self, live
    ) -> None:
        unfiltered = live.run(inventory.search_resources(live.client, page_size=1))
        assert unfiltered["total_count"] > 0

        by_kind = live.run(
            inventory.search_resources(
                live.client, resource_kind="VirtualMachine", page_size=5
            )
        )
        assert by_kind["total_count"] <= unfiltered["total_count"]
        assert all(
            item["resource_kind"] == "VirtualMachine" for item in by_kind["items"]
        )

        by_adapter = live.run(
            inventory.search_resources(live.client, adapter_kind="VMWARE", page_size=5)
        )
        assert by_adapter["total_count"] <= unfiltered["total_count"]
        assert all(item["adapter_kind"] == "VMWARE" for item in by_adapter["items"])

        absent = live.run(
            inventory.search_resources(
                live.client, name="no-such-resource-exists-here", page_size=1
            )
        )
        assert absent["total_count"] == 0
        assert absent["items"] == []

        one = live.run(inventory.search_resources(live.client, page_size=1))
        assert len(one["items"]) <= 1
        assert one["page_size"] == 1

    def test_an_unrecognized_parameter_is_silently_ignored_by_the_appliance(
        self, live, live_credentials
    ) -> None:
        """The measured hazard, re-proved against the appliance on every run.

        ``identifier`` is a plausible misspelling of a real filter. The
        appliance answers 200 with the whole unfiltered collection. If this
        assertion ever fails because the appliance started rejecting unknown
        parameters, the allowlist is still correct and this test is what tells
        us the ground moved.
        """

        unfiltered = live.run(inventory.search_resources(live.client, page_size=1))
        sample = live.run(inventory.search_resources(live.client, page_size=1))
        resource_id = sample["items"][0]["id"]

        async def misspelled() -> int:
            client = raw_client(live.client._target)  # noqa: SLF001
            try:
                token = await raw_token(client, live_credentials)
                response = await client.get(
                    "/api/resources",
                    params={"identifier": resource_id, "pageSize": 1},
                    headers={
                        "Authorization": f"OpsToken {token}",
                        "Accept": "application/json",
                    },
                )
                assert response.status_code == 200
                return response.json()["pageInfo"]["totalCount"]
            finally:
                await client.aclose()

        assert live.run(misspelled()) == unfiltered["total_count"]

    def test_the_client_refuses_that_same_parameter(self, live) -> None:
        with pytest.raises(OutboundContractViolation):
            live.run(
                live.client.request_read(
                    inventory.SEARCH_RESOURCES, query={"identifier": "anything"}
                )
            )

    def test_alert_filters_are_effective_only_in_the_post_body(self, live) -> None:
        everything = live.run(alerts.search_alerts(live.client, page_size=1))
        active = live.run(
            alerts.search_alerts(live.client, active_only=True, page_size=1)
        )
        critical = live.run(
            alerts.search_alerts(
                live.client, criticalities=["CRITICAL"], page_size=1
            )
        )
        assert active["total_count"] <= everything["total_count"]
        assert critical["total_count"] <= everything["total_count"]
        assert all(item["level"] == "CRITICAL" for item in critical["items"])


class TestReadSurface:
    def test_inventory_shapes(self, live) -> None:
        kinds = live.run(inventory.list_adapter_kinds(live.client))
        assert kinds["items"]
        assert all(item["key"] for item in kinds["items"])

        resource_kinds = live.run(
            inventory.list_resource_kinds(live.client, adapter_kind_key="VMWARE")
        )
        assert all(item["key"] for item in resource_kinds["items"])

        resources = live.run(inventory.search_resources(live.client, page_size=5))
        assert resources["items"]
        for item in resources["items"]:
            assert item["id"] and item["name"] and item["resource_kind"]
        detail = live.run(
            inventory.get_resource(
                live.client, resource_id=resources["items"][0]["id"]
            )
        )
        assert detail["resource"]["id"] == resources["items"][0]["id"]

    def test_metrics_shapes_and_window_control(self, live) -> None:
        vms = live.run(
            inventory.search_resources(
                live.client, resource_kind="VirtualMachine", page_size=1
            )
        )
        if not vms["items"]:
            pytest.skip("this target has no VirtualMachine resources")
        resource_id = vms["items"][0]["id"]

        keys = live.run(
            metrics_adapters.discover_stat_keys(live.client, resource_id=resource_id)
        )
        assert keys["items"]
        stat_key = keys["items"][0]["stat_key"]

        latest = live.run(
            metrics_adapters.get_latest_stats(
                live.client, resource_ids=[resource_id], stat_keys=[stat_key]
            )
        )
        for series in latest["series"]:
            assert len(series["timestamps_ms"]) == len(series["values"])

        # The window, not maxSamples, is what bounds a ranged read. A longer
        # window must not return fewer samples.
        end = latest["series"][0]["timestamps_ms"][-1] if latest["series"] else None
        if end is None:
            pytest.skip("this resource has no recent samples")
        short = live.run(
            metrics_adapters.get_ranged_stats(
                live.client,
                resource_ids=[resource_id],
                stat_keys=[stat_key],
                begin_ms=end - 60 * MINUTE_MS,
                end_ms=end,
            )
        )
        long = live.run(
            metrics_adapters.get_ranged_stats(
                live.client,
                resource_ids=[resource_id],
                stat_keys=[stat_key],
                begin_ms=end - 360 * MINUTE_MS,
                end_ms=end,
            )
        )
        assert long["sample_count"] >= short["sample_count"]
        assert short["sample_count"] <= samples_in_window(
            begin_ms=end - 60 * MINUTE_MS,
            end_ms=end,
            interval_type="MINUTES",
            quantifier=5,
        )

        supers = live.run(metrics_adapters.list_super_metrics(live.client, page_size=5))
        assert all(item["id"] for item in supers["items"])
        if supers["items"]:
            detail = live.run(
                metrics_adapters.get_super_metric(
                    live.client, super_metric_id=supers["items"][0]["id"]
                )
            )
            assert detail["super_metric"]["id"] == supers["items"][0]["id"]

    def test_alert_and_symptom_shapes(self, live) -> None:
        found = live.run(alerts.search_alerts(live.client, page_size=5))
        for item in found["items"]:
            assert item["id"] and item["definition_id"]
        if found["items"]:
            detail = live.run(
                alerts.get_alert(live.client, alert_id=found["items"][0]["id"])
            )
            assert detail["alert"]["id"] == found["items"][0]["id"]
            by_resource = live.run(
                alerts.list_resource_alerts(
                    live.client, resource_id=found["items"][0]["resource_id"], page_size=5
                )
            )
            assert by_resource["total_count"] <= found["total_count"]
            symptoms = live.run(
                alerts.list_resource_symptoms(
                    live.client, resource_id=found["items"][0]["resource_id"], page_size=5
                )
            )
            assert all(item["id"] for item in symptoms["items"])

        definitions = live.run(alerts.list_alert_definitions(live.client, page_size=5))
        assert all(item["id"] for item in definitions["items"])
        symptom_definitions = live.run(
            alerts.list_symptom_definitions(live.client, page_size=5)
        )
        assert all(item["id"] for item in symptom_definitions["items"])
        if symptom_definitions["items"]:
            detail = live.run(
                alerts.get_symptom_definition(
                    live.client,
                    symptom_definition_id=symptom_definitions["items"][0]["id"],
                )
            )
            assert detail["symptom_definition"]["id"]

    def test_report_definitions_only(self, live) -> None:
        listing = live.run(
            reports_adapters.list_report_definitions(live.client, page_size=5)
        )
        assert all(item["id"] and item["name"] for item in listing["items"])
        if listing["items"]:
            detail = live.run(
                reports_adapters.get_report_definition(
                    live.client, report_definition_id=listing["items"][0]["id"]
                )
            )
            assert detail["report_definition"]["id"] == listing["items"][0]["id"]


class TestGuards:
    def test_a_request_outside_the_read_set_fails_as_a_test_error(self, live) -> None:
        """A live test that tries to mutate never reaches the appliance."""

        async def attempt() -> None:
            client = raw_client(live.client._target)  # noqa: SLF001
            try:
                await client.post("/api/actions/someAction", json={})
            finally:
                await client.aclose()

        with pytest.raises(OutsideTheReadSet):
            live.run(attempt())

    def test_events_query_is_outside_the_read_set(self, live) -> None:
        """The endpoint that answers 403 for this role is not reachable here."""

        async def attempt() -> None:
            client = raw_client(live.client._target)  # noqa: SLF001
            try:
                await client.post("/api/events/query", json={})
            finally:
                await client.aclose()

        with pytest.raises(OutsideTheReadSet):
            live.run(attempt())

    def test_the_metrics_cap_refuses_before_reaching_the_appliance(self, live) -> None:
        with pytest.raises(ResultCapExceeded) as caught:
            live.run(
                metrics_adapters.get_latest_stats(
                    live.client,
                    resource_ids=[f"id-{i}" for i in range(MAX_METRICS_RESOURCES + 1)],
                    stat_keys=["cpu|demandmhz"],
                )
            )
        assert caught.value.cap_name == "MAX_METRICS_RESOURCES"

    def test_the_whole_run_needed_exactly_one_token(self, live) -> None:
        """Last test in file order, so it observes the whole run.

        Every read above went through one session-scoped client. If this ever
        reports more than one acquisition, either the refresh skew is wrong or
        something is re-authenticating on a status that is not 401.
        """

        assert live.client.token_acquisitions == 1
