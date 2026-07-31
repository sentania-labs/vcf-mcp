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
from vcf_ops_mcp.contracts import Capability
from vcf_ops_mcp.mcp_server import build_mcp_surface, implemented_scopes
from vcf_ops_mcp.runtime_repository import RuntimeRepository
from vcf_ops_mcp.skills import load_catalog
from vcf_ops_mcp.vcf.adapters import READ_ADAPTERS, READ_ALLOWLIST
from vcf_ops_mcp.vcf.client import TargetCredentials, VcfTargetClient

ROOT = Path(__file__).resolve().parents[1]
FAR_FUTURE_MS = 4_102_444_800_000


class SyntheticAppliance:
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
                            "resourceKinds": [
                                "VirtualMachine",
                                "HostSystem",
                            ],
                            "links": [{"href": "/not-exposed"}],
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected synthetic request: {path}")


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
    target = asyncio.run(
        runtime.create_target(
            name="fixture",
            fqdn="fixture.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=True,
        )
    )
    key = asyncio.run(
        runtime.create_api_key(
            label="integration",
            scopes=asyncio.run(runtime.grantable_scopes()),
            allowed_targets=frozenset({target.id}),
        )
    )

    def client_factory(
        target_record, credentials: TargetCredentials
    ) -> VcfTargetClient:
        return VcfTargetClient(
            target=target_record,
            credentials=credentials,
            allowlist=READ_ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{target_record.fqdn}/suite-api",
                transport=httpx.MockTransport(SyntheticAppliance()),
            ),
        )

    surface = build_mcp_surface(
        runtime_repository=runtime,
        audit_repository=audit,
        skills=load_catalog(ROOT / "skills"),
        digest_key=hashlib.sha256(b"synthetic-digest-key").digest(),
        public_base_url="http://testserver",
        client_factory=client_factory,
    )
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_surface=surface,
    )
    yield app, runtime, audit, target, key
    runtime.close()
    audit.close()


def rpc(client: TestClient, key: str, method: str, params: dict):
    return client.post(
        "/mcp/",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        },
    )


def test_bearer_auth_tool_listing_and_audited_inventory_read(
    mcp_system,
) -> None:
    app, _runtime, audit, target, key = mcp_system
    with TestClient(app) as client:
        rejected = client.post(
            "/mcp/",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert rejected.status_code == 401

        listed = rpc(client, key, "tools/list", {})
        assert listed.status_code == 200
        tool_names = {
            tool["name"] for tool in listed.json()["result"]["tools"]
        }
        assert len(tool_names) == len(READ_ADAPTERS) + 3
        assert "list_targets" in tool_names
        assert "list_adapter_kinds" in tool_names

        targets = rpc(
            client,
            key,
            "tools/call",
            {"name": "list_targets", "arguments": {}},
        )
        target_result = targets.json()["result"]["structuredContent"]
        assert target_result["state"] == "ok"
        assert target_result["result"]["targets"][0]["posture"] == "read_only"

        inventory = rpc(
            client,
            key,
            "tools/call",
            {
                "name": "list_adapter_kinds",
                "arguments": {
                    "target_id": str(target.id),
                    "arguments": {},
                },
            },
        )
        result = inventory.json()["result"]["structuredContent"]
        assert result["state"] == "ok"
        projected = result["result"]["items"][0]
        assert projected["key"] == "VMWARE"
        assert "links" not in projected

    records = asyncio.run(audit.recent_records(limit=20))
    assert [record.status.value for record in records[:4]] == [
        "ok",
        "attempt",
        "ok",
        "attempt",
    ]
    assert {record.tool_name for record in records[:4]} == {
        "list_targets",
        "list_adapter_kinds",
    }


def test_revocation_is_enforced_on_the_next_mcp_request(mcp_system) -> None:
    app, runtime, _audit, _target, key = mcp_system
    identity = asyncio.run(runtime.resolve_request_identity(key))
    assert identity is not None
    assert asyncio.run(runtime.revoke_api_key(identity.key_id))
    with TestClient(app) as client:
        response = rpc(client, key, "tools/list", {})
    assert response.status_code == 401


def test_capability_scope_is_enforced_inside_the_dispatcher(
    mcp_system,
) -> None:
    app, runtime, audit, target, _key = mcp_system
    restricted = asyncio.run(
        runtime.create_api_key(
            label="target-discovery-only",
            scopes=frozenset({Capability.READ_TARGETS}),
            allowed_targets=frozenset({target.id}),
        )
    )
    with TestClient(app) as client:
        response = rpc(
            client,
            restricted,
            "tools/call",
            {
                "name": "list_adapter_kinds",
                "arguments": {
                    "target_id": str(target.id),
                    "arguments": {},
                },
            },
        )
    result = response.json()["result"]["structuredContent"]
    assert result["state"] == "denied"
    assert result["error_code"] == "scope_denied"
    records = asyncio.run(audit.recent_records(limit=1))
    assert records[0].status.value == "denied"
    assert records[0].error_code == "scope_denied"


def test_skill_resources_and_prompts_require_read_skills(mcp_system) -> None:
    app, runtime, _audit, target, full_key = mcp_system
    restricted = asyncio.run(
        runtime.create_api_key(
            label="target-discovery-only",
            scopes=frozenset({Capability.READ_TARGETS}),
            allowed_targets=frozenset({target.id}),
        )
    )
    resource_params = {"uri": "skill://metrics-query-patterns/current"}
    prompt_params = {
        "name": "use_metrics-query-patterns",
        "arguments": {},
    }

    with TestClient(app) as client:
        denied_resource = rpc(
            client, restricted, "resources/read", resource_params
        )
        denied_prompt = rpc(
            client, restricted, "prompts/get", prompt_params
        )
        allowed_resource = rpc(
            client, full_key, "resources/read", resource_params
        )
        allowed_prompt = rpc(
            client, full_key, "prompts/get", prompt_params
        )

    assert "error" in denied_resource.json()
    assert "read:skills" in denied_resource.json()["error"]["message"]
    assert "error" in denied_prompt.json()
    assert "read:skills" in denied_prompt.json()["error"]["message"]
    assert "Metrics Query Patterns" in (
        allowed_resource.json()["result"]["contents"][0]["text"]
    )
    assert "Metrics Query Patterns" in (
        allowed_prompt.json()["result"]["messages"][0]["content"]["text"]
    )
