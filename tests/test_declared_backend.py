from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from vcf_ops_mcp.backend_packs import load_backend_packs
from vcf_ops_mcp.contracts import (
    BackendKind,
    ConfigurationGeneration,
    TargetId,
    TargetPosture,
    TargetRecord,
)
from vcf_ops_mcp.declared_backend import DeclaredBackendClient
from vcf_ops_mcp.vcf.client import TargetCredentials
from vcf_ops_mcp.vcf.errors import ResultCapExceeded


def target(backend: BackendKind) -> TargetRecord:
    return TargetRecord(
        id=TargetId(f"fixture-{backend.value}"),
        name=f"fixture-{backend.value}",
        fqdn=f"{backend.value}.example.internal",
        posture=TargetPosture.READ_ONLY,
        is_prod=False,
        verify_ssl=False,
        auth_source="LOCAL",
        configuration_generation=ConfigurationGeneration(1),
        backend=backend,
    )


@pytest.mark.asyncio
async def test_basic_pack_renders_only_declared_path_query_and_projection() -> None:
    pack = load_backend_packs()[BackendKind.NSX]

    async def appliance(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/policy/api/v1/infra/segments"
        assert dict(request.url.params) == {"page_size": "25"}
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "segment-1",
                        "display_name": "fixture-segment",
                        "credential": "must-not-pass",
                    }
                ],
                "result_count": 1,
                "private": "must-not-pass",
            },
        )

    client = DeclaredBackendClient(
        target=target(BackendKind.NSX),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://nsx.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared(
            "list_nsx_segments",
            {"cursor": None, "page_size": 25},
        )
    finally:
        await client.aclose()

    assert result == {
        "results": [{"id": "segment-1", "display_name": "fixture-segment"}],
        "result_count": 1,
    }


@pytest.mark.asyncio
async def test_gzip_compressed_upstream_response_decodes_once() -> None:
    import gzip
    import json

    pack = load_backend_packs()[BackendKind.NSX]
    payload = {"results": [{"id": "segment-1"}], "result_count": 1}

    async def appliance(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(json.dumps(payload).encode()),
            headers={
                "content-encoding": "gzip",
                "content-type": "application/json",
            },
        )

    client = DeclaredBackendClient(
        target=target(BackendKind.NSX),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://nsx.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared(
            "list_nsx_segments",
            {"cursor": None, "page_size": None},
        )
    finally:
        await client.aclose()

    assert result == payload


@pytest.mark.asyncio
async def test_sddc_token_reauthentication_is_bounded_to_one_retry() -> None:
    pack = load_backend_packs()[BackendKind.SDDC_MANAGER]
    token_count = 0
    read_count = 0

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal token_count, read_count
        if request.url.path == "/v1/tokens":
            token_count += 1
            assert request.method == "POST"
            return httpx.Response(201, json={"accessToken": f"token-{token_count}"})
        assert request.url.path == "/v1/system"
        assert request.headers["authorization"] == f"Bearer token-{token_count}"
        read_count += 1
        if read_count == 1:
            return httpx.Response(401, json={"error": "synthetic expiry"})
        return httpx.Response(200, json={"id": "system", "version": "9.1"})

    client = DeclaredBackendClient(
        target=target(BackendKind.SDDC_MANAGER),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://sddc-manager.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared("get_sddc_system", {})
    finally:
        await client.aclose()

    assert result == {"id": "system", "version": "9.1"}
    assert token_count == 2
    assert read_count == 2


@pytest.mark.asyncio
async def test_log_exchange_and_nested_body_template_are_fixture_proven() -> None:
    pack = load_backend_packs()[BackendKind.LOG_MANAGEMENT]

    async def appliance(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/acquire"):
            return httpx.Response(200, json={"token": "ops-token"})
        if request.url.path.endswith("/token/exchange"):
            assert request.headers["authorization"] == "OpsToken ops-token"
            assert request.read() == b'{"serviceKeys":["ops-li"]}'
            return httpx.Response(200, json={"accessToken": "log-token"})
        assert request.url.path == "/api/v2/logs/search"
        assert request.headers["x-jwt-token"] == "log-token"
        assert request.method == "POST"
        assert request.read() == (
            b'{"query":{"match_phrase":{"hostname":"esx-01"}},"size":25}'
        )
        return httpx.Response(
            200,
            json={
                "hits": [{"hostname": "esx-01", "text": "fixture log"}],
                "total": 1,
                "password": "must-not-pass",
            },
        )

    client = DeclaredBackendClient(
        target=target(BackendKind.LOG_MANAGEMENT),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://logs.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared(
            "search_logs_by_hostname",
            {"hostname": "esx-01", "size": 25},
        )
    finally:
        await client.aclose()

    assert result == {
        "hits": [{"hostname": "esx-01", "text": "fixture log"}],
        "total": 1,
    }


@pytest.mark.asyncio
async def test_log_agent_secret_values_never_enter_the_projected_result() -> None:
    pack = load_backend_packs()[BackendKind.LOG_MANAGEMENT]

    async def appliance(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/acquire"):
            return httpx.Response(200, json={"token": "ops-token"})
        if request.url.path.endswith("/token/exchange"):
            return httpx.Response(200, json={"accessToken": "log-token"})
        assert request.url.path == "/api/v2/agent/secrets"
        return httpx.Response(
            200,
            json={
                "id": "secret-1",
                "name": "fixture agent secret",
                "status": "ACTIVE",
                "value": "must-not-pass",
                "password": "must-not-pass",
                "token": "must-not-pass",
                "items": [
                    {
                        "id": "secret-2",
                        "name": "nested fixture agent secret",
                        "value": "must-not-pass",
                    }
                ],
            },
        )

    client = DeclaredBackendClient(
        target=target(BackendKind.LOG_MANAGEMENT),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://logs.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared(
            "list_log_agent_secrets", {"pageable": None}
        )
    finally:
        await client.aclose()

    assert result == {
        "id": "secret-1",
        "name": "fixture agent secret",
        "status": "ACTIVE",
        "items": [
            {
                "id": "secret-2",
                "name": "nested fixture agent secret",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend", "tool_name", "read_path", "acquires_token"),
    [
        (
            BackendKind.FLEET_LCM,
            "get_fleet_health",
            "/fleet-lcm/v1/health",
            False,
        ),
        (
            BackendKind.OPS_NETWORKS,
            "get_networks_version",
            "/api/ni/info/version",
            True,
        ),
    ],
)
async def test_static_and_ops_acquired_bearer_shapes_are_fixture_proven(
    backend: BackendKind,
    tool_name: str,
    read_path: str,
    acquires_token: bool,
) -> None:
    pack = load_backend_packs()[backend]
    released_tokens: list[str] = []

    async def appliance(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/acquire"):
            assert acquires_token
            return httpx.Response(200, json={"token": "acquired-token"})
        if request.url.path.endswith("/token/release"):
            assert acquires_token
            released_tokens.append(request.headers["authorization"])
            return httpx.Response(200)
        assert request.url.path == read_path
        expected = "acquired-token" if acquires_token else "synthetic-password"
        assert request.headers["authorization"] == f"Bearer {expected}"
        return httpx.Response(200, json={"status": "UP", "version": "9.1"})

    client = DeclaredBackendClient(
        target=target(backend),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url=f"https://{backend.value}.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        result = await client.request_declared(tool_name, {})
    finally:
        await client.aclose()

    assert result == {"status": "UP", "version": "9.1"}
    assert released_tokens == (["OpsToken acquired-token"] if acquires_token else [])


@pytest.mark.asyncio
async def test_ops_bearer_releases_rejected_and_shutdown_tokens() -> None:
    pack = load_backend_packs()[BackendKind.OPS_NETWORKS]
    acquisitions = 0
    reads = 0
    released_tokens: list[str] = []

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal acquisitions, reads
        if request.url.path.endswith("/token/acquire"):
            acquisitions += 1
            return httpx.Response(200, json={"token": f"ops-token-{acquisitions}"})
        if request.url.path.endswith("/token/release"):
            released_tokens.append(request.headers["authorization"])
            return httpx.Response(200)
        assert request.url.path == "/api/ni/info/version"
        reads += 1
        if reads == 1:
            return httpx.Response(401, json={"error": "synthetic expiry"})
        return httpx.Response(200, json={"version": "9.1"})

    client = DeclaredBackendClient(
        target=target(BackendKind.OPS_NETWORKS),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://ops-networks.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    result = await client.request_declared("get_networks_version", {})
    await client.aclose()

    assert result == {"version": "9.1"}
    assert acquisitions == 2
    assert reads == 2
    assert released_tokens == ["OpsToken ops-token-1", "OpsToken ops-token-2"]


@pytest.mark.asyncio
async def test_vsan_session_header_shape_is_fixture_proven() -> None:
    pack = load_backend_packs()[BackendKind.VSAN_DP]
    session_deleted = False

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal session_deleted
        if request.url.path == "/api/session" and request.method == "POST":
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(201, json="vsan-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            session_deleted = True
            return httpx.Response(204)
        assert request.url.path == "/api/snapservice/info/about"
        assert request.headers["vmware-api-session-id"] == "vsan-session"
        return httpx.Response(200, json={"version": "9.1", "status": "UP"})

    client = DeclaredBackendClient(
        target=target(BackendKind.VSAN_DP),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://vsan-dp.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    result = await client.request_declared("get_vsan_snapshot_service_info", {})
    await client.aclose()

    assert result == {"version": "9.1", "status": "UP"}
    assert session_deleted is True


@pytest.mark.asyncio
async def test_nested_response_list_cap_is_enforced() -> None:
    pack = replace(
        load_backend_packs()[BackendKind.NSX],
        caps={"max_response_bytes": 1_048_576, "max_list_items": 2},
    )

    async def appliance(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"id": "one"}, {"id": "two"}, {"id": "three"}]},
        )

    client = DeclaredBackendClient(
        target=target(BackendKind.NSX),
        credentials=TargetCredentials("synthetic-user", "synthetic-password"),
        pack=pack,
        http_client=httpx.AsyncClient(
            base_url="https://nsx.example.internal",
            transport=httpx.MockTransport(appliance),
        ),
    )
    try:
        with pytest.raises(ResultCapExceeded):
            await client.request_declared("list_nsx_segments", {})
    finally:
        await client.aclose()
