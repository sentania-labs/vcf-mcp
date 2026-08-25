from __future__ import annotations

import asyncio

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
from vcf_ops_mcp.vcenter import VcenterTargetClient, list_vcenter_vms
from vcf_ops_mcp.vcf.client import TargetCredentials
from vcf_ops_mcp.vcf.errors import (
    PermissionDeniedError,
    ReauthenticationExhausted,
    TargetConfigurationSuperseded,
)


def target() -> TargetRecord:
    return TargetRecord(
        id=TargetId("fixture-vcenter"),
        name="fixture-vcenter",
        fqdn="vcenter.example.internal",
        posture=TargetPosture.READ_ONLY,
        is_prod=False,
        verify_ssl=False,
        auth_source="LOCAL",
        configuration_generation=ConfigurationGeneration(1),
        backend=BackendKind.VCENTER,
    )


def client_for(handler) -> VcenterTargetClient:
    pack = load_backend_packs()[BackendKind.VCENTER]
    record = target()
    return VcenterTargetClient(
        target=record,
        credentials=TargetCredentials("synthetic-user", "synthetic-password", "LOCAL"),
        tools={tool.name: tool for tool in pack.tools},
        http_client=httpx.AsyncClient(
            base_url=f"https://{record.fqdn}",
            transport=httpx.MockTransport(handler),
        ),
    )


@pytest.mark.asyncio
async def test_vcenter_uses_basic_session_then_projects_inventory() -> None:
    sessions = 0

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal sessions
        if request.url.path == "/api/session" and request.method == "POST":
            sessions += 1
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(201, json="fixture-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        assert request.headers["vmware-api-session-id"] == "fixture-session"
        return httpx.Response(
            200,
            json=[
                {
                    "vm": "vm-101",
                    "name": "fixture-vm",
                    "power_state": "POWERED_ON",
                    "cpu_count": 4,
                    "memory_size_MiB": 8192,
                    "not_in_projection": "hidden",
                }
            ],
        )

    client = client_for(appliance)
    try:
        first = await list_vcenter_vms(client)
        second = await list_vcenter_vms(client)
    finally:
        await client.aclose()
    assert sessions == 1
    assert first == second
    assert first["items"][0] == {
        "vm": "vm-101",
        "name": "fixture-vm",
        "power_state": "POWERED_ON",
        "cpu_count": 4,
        "memory_size_MiB": 8192,
    }


@pytest.mark.asyncio
async def test_vcenter_retries_one_401_then_stops() -> None:
    sessions = 0
    reads = 0

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal sessions, reads
        if request.url.path == "/api/session" and request.method == "POST":
            sessions += 1
            return httpx.Response(201, json=f"fixture-session-{sessions}")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        reads += 1
        return httpx.Response(401, json={"error": "synthetic refusal"})

    client = client_for(appliance)
    try:
        with pytest.raises(ReauthenticationExhausted):
            await list_vcenter_vms(client)
    finally:
        await client.aclose()
    assert sessions == 2
    assert reads == 2


@pytest.mark.asyncio
async def test_vcenter_does_not_reauthenticate_on_403() -> None:
    sessions = 0

    async def appliance(request: httpx.Request) -> httpx.Response:
        nonlocal sessions
        if request.url.path == "/api/session" and request.method == "POST":
            sessions += 1
            return httpx.Response(201, json="fixture-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(403, text="synthetic forbidden")

    client = client_for(appliance)
    try:
        with pytest.raises(PermissionDeniedError):
            await list_vcenter_vms(client)
    finally:
        await client.aclose()
    assert sessions == 1


@pytest.mark.asyncio
async def test_vcenter_refuses_unsafe_path_identifiers_before_network() -> None:
    calls = 0

    async def appliance(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = client_for(appliance)
    try:
        with pytest.raises(ValueError, match="unsafe path"):
            await client.request_read(
                "get_vcenter_vm", path_parameters={"vm": "../session"}
            )
    finally:
        await client.aclose()
    assert calls == 0


@pytest.mark.asyncio
async def test_vcenter_drain_discards_a_result_from_replaced_configuration() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def appliance(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            return httpx.Response(201, json="fixture-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        started.set()
        await release.wait()
        return httpx.Response(200, json=[])

    client = client_for(appliance)
    call = asyncio.create_task(list_vcenter_vms(client))
    await started.wait()
    assert client.mark_closed() == 1
    draining = asyncio.create_task(client.drain())
    release.set()
    await draining
    with pytest.raises(TargetConfigurationSuperseded):
        await call
    await client.aclose()


@pytest.mark.asyncio
async def test_vcenter_cancel_unwinds_inflight_work() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def appliance(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            return httpx.Response(201, json="fixture-session")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        started.set()
        await release.wait()
        return httpx.Response(200, json=[])

    client = client_for(appliance)
    call = asyncio.create_task(list_vcenter_vms(client))
    await started.wait()
    assert client.mark_closed() == 1
    assert await client.cancel() == 1
    with pytest.raises(asyncio.CancelledError):
        await call
    await client.aclose()
