from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from vcf_ops_mcp.app import create_app
from vcf_ops_mcp.audit import SqliteAuditRepository
from vcf_ops_mcp.backend_packs import load_backend_packs
from vcf_ops_mcp.contracts import BackendKind, Capability
from vcf_ops_mcp.mcp_server import build_mcp_surfaces, implemented_scopes
from vcf_ops_mcp.runtime_repository import RuntimeRepository
from vcf_ops_mcp.skills import load_catalog
from vcf_ops_mcp.vcenter import VcenterTargetClient
from vcf_ops_mcp.vcf.adapters import ADAPTERS_BY_TOOL_NAME
from vcf_ops_mcp.vcf.client import TargetCredentials, VcfTargetClient
from vcf_ops_mcp.vcf.outbound import OutboundAllowlist


ROOT = Path(__file__).resolve().parents[1]
FAR_FUTURE_MS = 4_102_444_800_000


class SyntheticOps:
    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/suite-api")
        if path == "/api/auth/token/acquire":
            return httpx.Response(
                200,
                json={"token": "synthetic-token", "validity": FAR_FUTURE_MS},
            )
        if path == "/api/auth/token/release":
            return httpx.Response(200, json={})
        if path == "/api/adapterkinds":
            return httpx.Response(
                200,
                json={
                    "adapter-kind": [
                        {
                            "key": "VMWARE",
                            "name": "VMware vSphere",
                            "description": "synthetic",
                            "adapterKindType": "GENERAL",
                            "resourceKinds": ["VirtualMachine"],
                            "links": [{"href": "/not-exposed"}],
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected Operations request: {path}")


class SyntheticVcenter:
    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            assert request.headers.get("authorization", "").startswith("Basic ")
            return httpx.Response(201, json="synthetic-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        assert request.headers["vmware-api-session-id"] == "synthetic-session"
        if request.url.path == "/api/vcenter/vm":
            return httpx.Response(
                200,
                json=[
                    {
                        "vm": "vm-101",
                        "name": "fixture-vm",
                        "power_state": "POWERED_ON",
                        "cpu_count": 4,
                        "memory_size_MiB": 8192,
                        "secret_extra": "not projected",
                    }
                ],
            )
        raise AssertionError(f"unexpected vCenter request: {request.url.path}")


@pytest.fixture
def mcp_system(tmp_path: Path):
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
    )
    runtime.bootstrap()
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    ops = asyncio.run(
        runtime.create_target(
            name="fixture-ops",
            fqdn="ops.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.OPS,
        )
    )
    vcenter = asyncio.run(
        runtime.create_target(
            name="fixture-vcenter",
            fqdn="vcenter.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.VCENTER,
        )
    )
    key = asyncio.run(
        runtime.create_api_key(
            label="integration",
            scopes=asyncio.run(runtime.grantable_scopes()),
            allowed_targets=frozenset({ops.id, vcenter.id}),
            allowed_endpoints=frozenset({"ops", "vcenter", "vcf"}),
        )
    )
    packs = load_backend_packs()

    def ops_factory(target, credentials: TargetCredentials, _root_ca):
        contracts = [
            ADAPTERS_BY_TOOL_NAME[tool.name].read_contract
            for tool in packs[BackendKind.OPS].tools
        ]
        return VcfTargetClient(
            target=target,
            credentials=credentials,
            allowlist=OutboundAllowlist(contracts),
            http_client=httpx.AsyncClient(
                base_url=f"https://{target.fqdn}/suite-api",
                transport=httpx.MockTransport(SyntheticOps()),
            ),
        )

    def vcenter_factory(target, credentials: TargetCredentials, _root_ca):
        pack = packs[BackendKind.VCENTER]
        return VcenterTargetClient(
            target=target,
            credentials=credentials,
            tools={tool.name: tool for tool in pack.tools},
            http_client=httpx.AsyncClient(
                base_url=f"https://{target.fqdn}",
                transport=httpx.MockTransport(SyntheticVcenter()),
            ),
        )

    surfaces = build_mcp_surfaces(
        runtime_repository=runtime,
        audit_repository=audit,
        skills=load_catalog(ROOT / "skills"),
        digest_key=hashlib.sha256(b"synthetic-digest-key").digest(),
        public_base_url="http://testserver",
        client_factories={
            BackendKind.OPS: ops_factory,
            BackendKind.VCENTER: vcenter_factory,
        },
    )
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_surfaces=surfaces,
    )
    yield app, runtime, audit, ops, vcenter, key
    runtime.close()
    audit.close()


def rpc(
    client: TestClient,
    endpoint: str,
    key: str,
    method: str,
    params: dict,
    *,
    caller_id: str | None = None,
):
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if caller_id:
        headers["X-VCF-Caller-ID"] = caller_id
    return client.post(
        f"/{endpoint}/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


def structured(response: httpx.Response) -> dict:
    payload = response.json()
    assert "structuredContent" in payload.get("result", {}), payload
    return payload["result"]["structuredContent"]


def test_endpoint_surfaces_are_flat_typed_and_backend_specific(mcp_system) -> None:
    app, _runtime, _audit, _ops, _vcenter, key = mcp_system
    with TestClient(app) as client:
        ops_tools = rpc(client, "ops", key, "tools/list", {}).json()["result"]["tools"]
        vcenter_tools = rpc(client, "vcenter", key, "tools/list", {}).json()["result"][
            "tools"
        ]
        vcf_tools = rpc(client, "vcf", key, "tools/list", {}).json()["result"]["tools"]

    assert len(ops_tools) == 19
    assert {tool["name"] for tool in vcenter_tools} == {
        "list_vcenter_vms",
        "get_vcenter_vm",
        "list_vcenter_hosts",
        "get_vcenter_session",
    }
    assert "list_wired_backends" in {tool["name"] for tool in vcf_tools}
    assert "list_adapter_kinds" not in {tool["name"] for tool in vcf_tools}
    search_schema = next(
        tool["inputSchema"] for tool in ops_tools if tool["name"] == "search_resources"
    )
    assert "name" in search_schema["properties"]
    assert "arguments" not in search_schema["properties"]
    vm_schema = next(
        tool["inputSchema"]
        for tool in vcenter_tools
        if tool["name"] == "get_vcenter_vm"
    )
    assert set(vm_schema["required"]) == {"target_id", "vm"}


def test_typed_calls_return_fixture_data_from_both_products(mcp_system) -> None:
    app, _runtime, audit, ops, vcenter, key = mcp_system
    with TestClient(app) as client:
        ops_result = structured(
            rpc(
                client,
                "ops",
                key,
                "tools/call",
                {"name": "list_adapter_kinds", "arguments": {"target_id": str(ops.id)}},
            )
        )
        vcenter_result = structured(
            rpc(
                client,
                "vcenter",
                key,
                "tools/call",
                {
                    "name": "list_vcenter_vms",
                    "arguments": {"target_id": str(vcenter.id)},
                },
            )
        )

    assert ops_result["state"] == "ok"
    assert ops_result["result"]["items"][0]["key"] == "VMWARE"
    assert vcenter_result["state"] == "ok"
    vm = vcenter_result["result"]["items"][0]
    assert vm["vm"] == "vm-101"
    assert "secret_extra" not in vm
    records = asyncio.run(audit.recent_records(limit=4))
    assert {record.endpoint_name for record in records} == {"ops", "vcenter"}
    assert {record.pack_id for record in records} == {
        "sentania.ops.read",
        "sentania.vcenter.inventory",
    }
    assert all(record.pack_digest for record in records)


def test_wrong_backend_target_is_an_audited_denial(mcp_system) -> None:
    app, _runtime, _audit, _ops, vcenter, key = mcp_system
    with TestClient(app) as client:
        result = structured(
            rpc(
                client,
                "ops",
                key,
                "tools/call",
                {
                    "name": "list_adapter_kinds",
                    "arguments": {"target_id": str(vcenter.id)},
                },
            )
        )
    assert result["state"] == "denied"
    assert result["error_code"] == "endpoint_target_mismatch"


def test_management_history_requires_key_and_caller_identity(mcp_system) -> None:
    app, _runtime, _audit, ops, _vcenter, key = mcp_system
    with TestClient(app) as client:
        rpc(
            client,
            "ops",
            key,
            "tools/call",
            {"name": "list_adapter_kinds", "arguments": {"target_id": str(ops.id)}},
            caller_id="fixture-agent",
        )
        without_caller = structured(
            rpc(
                client,
                "vcf",
                key,
                "tools/call",
                {"name": "get_call_history", "arguments": {}},
            )
        )
        with_caller = structured(
            rpc(
                client,
                "vcf",
                key,
                "tools/call",
                {"name": "get_call_history", "arguments": {}},
                caller_id="fixture-agent",
            )
        )
    assert without_caller["result"]["history"] == []
    assert without_caller["result"]["caller_identity_present"] is False
    assert with_caller["result"]["history"][0]["tool"] == "list_adapter_kinds"


def test_revocation_and_scope_are_enforced_on_each_endpoint(mcp_system) -> None:
    app, runtime, _audit, ops, _vcenter, key = mcp_system
    restricted = asyncio.run(
        runtime.create_api_key(
            label="management-only",
            scopes=frozenset({Capability.READ_TARGETS}),
            allowed_targets=frozenset({ops.id}),
            allowed_endpoints=frozenset({"ops", "vcf"}),
        )
    )
    with TestClient(app) as client:
        denied = structured(
            rpc(
                client,
                "ops",
                restricted,
                "tools/call",
                {"name": "list_adapter_kinds", "arguments": {"target_id": str(ops.id)}},
            )
        )
        identity = asyncio.run(runtime.resolve_request_identity(key))
        assert identity is not None
        asyncio.run(runtime.revoke_api_key(identity.key_id))
        rejected = rpc(client, "ops", key, "tools/list", {})
    assert denied["error_code"] == "scope_denied"
    assert rejected.status_code == 401


def test_skill_resources_live_on_management_endpoint(mcp_system) -> None:
    app, _runtime, _audit, _ops, _vcenter, key = mcp_system
    with TestClient(app) as client:
        resource = rpc(
            client,
            "vcf",
            key,
            "resources/read",
            {"uri": "skill://metrics-query-patterns/current"},
        )
    assert "Metrics Query Patterns" in resource.json()["result"]["contents"][0]["text"]


def test_unregistered_backend_contributes_no_endpoint(tmp_path: Path) -> None:
    runtime = RuntimeRepository(
        tmp_path / "data.sqlite3",
        tmp_path / "keyring.json",
        grantable_scopes=implemented_scopes(),
    )
    runtime.bootstrap()
    asyncio.run(
        runtime.create_target(
            name="ops-only",
            fqdn="ops-only.example.internal",
            username="synthetic",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.OPS,
        )
    )
    audit = SqliteAuditRepository(tmp_path / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    surfaces = build_mcp_surfaces(
        runtime_repository=runtime,
        audit_repository=audit,
        skills=load_catalog(ROOT / "skills"),
        digest_key=hashlib.sha256(b"digest").digest(),
        public_base_url="http://testserver",
    )
    try:
        assert set(surfaces.by_endpoint) == {"ops", "vcf"}
    finally:
        runtime.close()
        audit.close()
