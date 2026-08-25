"""Fixture-tested vCenter read client and static adapter handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

import httpx

from vcf_ops_mcp.backend_packs import PackTool
from vcf_ops_mcp.contracts import ConfigurationGeneration, TargetId, TargetRecord
from vcf_ops_mcp.vcf.caps import MAX_UPSTREAM_RESPONSE_BYTES
from vcf_ops_mcp.vcf.client import TargetCredentials, build_tls_verifier
from vcf_ops_mcp.vcf.errors import (
    AuthenticationError,
    PermissionDeniedError,
    ReauthenticationExhausted,
    ResultCapExceeded,
    TargetConfigurationSuperseded,
    UpstreamProtocolError,
    UpstreamStatusError,
    UpstreamUnavailableError,
)
from vcf_ops_mcp.vcf.outbound import _SAFE_PATH_VALUE


SESSION_PATH = "/api/session"
SESSION_HEADER = "vmware-api-session-id"
MAX_REAUTHENTICATIONS_PER_REQUEST = 1
DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=60, write=30, pool=10)
DEFAULT_MAX_LIST_ITEMS = 4_000


class VcenterTargetClient:
    """One session-authenticated vCenter client for one target generation."""

    def __init__(
        self,
        *,
        target: TargetRecord,
        credentials: TargetCredentials,
        tools: Mapping[str, PackTool],
        caps: Mapping[str, int] | None = None,
        root_ca_pem: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._target = target
        self._credentials = credentials
        self._tools = dict(tools)
        declared_caps = caps or {}
        self._max_list_items = int(
            declared_caps.get("max_list_items", DEFAULT_MAX_LIST_ITEMS)
        )
        self._max_response_bytes = int(
            declared_caps.get("max_response_bytes", MAX_UPSTREAM_RESPONSE_BYTES)
        )
        self._http = http_client or httpx.AsyncClient(
            base_url=f"https://{target.fqdn}",
            verify=build_tls_verifier(target, root_ca_pem),
            timeout=DEFAULT_TIMEOUT,
        )
        self._session_id: str | None = None
        self._session_generation = 0
        self._auth_lock = asyncio.Lock()
        self._closed = False
        self._inflight: set[asyncio.Task[object]] = set()

    @property
    def target_id(self) -> TargetId:
        return self._target.id

    @property
    def configuration_generation(self) -> ConfigurationGeneration:
        return self._target.configuration_generation

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def request_read(
        self,
        tool_name: str,
        *,
        path_parameters: Mapping[str, str] | None = None,
        query: Mapping[str, object] | None = None,
    ) -> object:
        if self._closed:
            raise TargetConfigurationSuperseded(
                "the target configuration was replaced",
                target_id=self._target.id,
            )
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"vCenter tool {tool_name!r} is not in the pack")
        path = _render_pack_path(tool, path_parameters or {})
        checked_query = _check_pack_query(tool, query or {})
        task = asyncio.current_task()
        if task is not None:
            self._inflight.add(task)
        try:
            reauthentications = 0
            while True:
                session_id, generation = await self._session()
                response = await self._send(path, checked_query, session_id)
                if response.status_code == 401:
                    if reauthentications >= MAX_REAUTHENTICATIONS_PER_REQUEST:
                        raise ReauthenticationExhausted(
                            "a newly created vCenter session was refused",
                            target_id=self._target.id,
                        )
                    reauthentications += 1
                    self._refuse_if_superseded()
                    await self._reacquire(generation)
                    continue
                if response.status_code == 403:
                    raise PermissionDeniedError(
                        "vCenter refused this read for the credential's role",
                        target_id=self._target.id,
                        path=path,
                    )
                if response.status_code >= 400:
                    raise UpstreamStatusError(
                        f"vCenter answered {response.status_code} for this read",
                        status_code=response.status_code,
                        target_id=self._target.id,
                        path=path,
                    )
                decoded = _decode_json(response, self._target.id)
                self._refuse_if_superseded()
                return decoded
        finally:
            if task is not None:
                self._inflight.discard(task)

    async def _session(self) -> tuple[str, int]:
        if self._session_id is not None:
            return self._session_id, self._session_generation
        async with self._auth_lock:
            if self._session_id is None:
                await self._acquire_locked()
            assert self._session_id is not None
            return self._session_id, self._session_generation

    async def _reacquire(self, observed_generation: int) -> None:
        async with self._auth_lock:
            if self._session_generation != observed_generation:
                return
            await self._acquire_locked()

    async def _acquire_locked(self) -> None:
        username, password = self._credentials.basic_auth_tuple()
        try:
            response = await self._http.post(
                SESSION_PATH,
                auth=httpx.BasicAuth(username, password),
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"vCenter could not be reached ({type(exc).__name__})",
                target_id=self._target.id,
            ) from None
        if response.status_code == 401:
            raise AuthenticationError(
                "vCenter refused these credentials",
                target_id=self._target.id,
            )
        if response.status_code >= 400:
            raise UpstreamStatusError(
                f"vCenter session creation answered {response.status_code}",
                status_code=response.status_code,
                target_id=self._target.id,
                path=SESSION_PATH,
            )
        session_id = _decode_json(response, self._target.id)
        if not isinstance(session_id, str) or not session_id:
            raise UpstreamProtocolError(
                "vCenter session creation returned no session id",
                target_id=self._target.id,
            )
        self._session_id = session_id
        self._session_generation += 1

    async def _send(
        self, path: str, query: Mapping[str, object], session_id: str
    ) -> httpx.Response:
        try:
            request = self._http.build_request(
                "GET",
                path,
                params=query or None,
                headers={
                    "Accept": "application/json",
                    SESSION_HEADER: session_id,
                },
            )
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"vCenter could not be reached ({type(exc).__name__})",
                target_id=self._target.id,
            ) from None
        try:
            content = await self._read_capped(response)
        finally:
            await response.aclose()
        return httpx.Response(
            status_code=response.status_code,
            headers=_rebuffered_headers(response.headers),
            content=content,
            request=request,
        )

    async def _read_capped(self, response: httpx.Response) -> bytes:
        buffered = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                buffered.extend(chunk)
                if len(buffered) > self._max_response_bytes:
                    raise ResultCapExceeded(
                        cap_name="max_response_bytes",
                        cap_value=self._max_response_bytes,
                        requested=len(buffered),
                        unit="bytes",
                        target_id=self._target.id,
                    )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"vCenter could not be reached ({type(exc).__name__})",
                target_id=self._target.id,
            ) from None
        return bytes(buffered)

    def enforce_list_cap(self, item_count: int) -> None:
        if item_count > self._max_list_items:
            raise ResultCapExceeded(
                cap_name="max_list_items",
                cap_value=self._max_list_items,
                requested=item_count,
                unit="items",
                target_id=self._target.id,
            )

    def mark_closed(self) -> int:
        self._closed = True
        return len(self._inflight)

    def _refuse_if_superseded(self) -> None:
        if self._closed:
            raise TargetConfigurationSuperseded(
                "the target configuration was replaced while this request was running",
                target_id=self._target.id,
                observed_generation=int(self._target.configuration_generation),
            )

    async def drain(self) -> None:
        tasks = [task for task in self._inflight if task is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def cancel(self) -> int:
        tasks = [task for task in self._inflight if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    async def aclose(self) -> None:
        session_id = self._session_id
        self._session_id = None
        if session_id:
            try:
                await self._http.delete(
                    SESSION_PATH, headers={SESSION_HEADER: session_id}
                )
            except httpx.HTTPError:
                pass
        await self._http.aclose()


async def list_vcenter_vms(
    client: VcenterTargetClient,
    *,
    names: Sequence[str] | None = None,
    power_states: Sequence[str] | None = None,
    vms: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
    hosts: Sequence[str] | None = None,
    clusters: Sequence[str] | None = None,
    resource_pools: Sequence[str] | None = None,
) -> dict[str, object]:
    raw = await client.request_read(
        "list_vcenter_vms",
        query={
            "names": names,
            "power_states": power_states,
            "vms": vms,
            "folders": folders,
            "datacenters": datacenters,
            "hosts": hosts,
            "clusters": clusters,
            "resource_pools": resource_pools,
        },
    )
    if not isinstance(raw, list):
        raise UpstreamProtocolError(
            "vCenter VM list was not a list", target_id=client.target_id
        )
    client.enforce_list_cap(len(raw))
    return {"items": [_project_vm_summary(item) for item in raw], "count": len(raw)}


async def get_vcenter_vm(client: VcenterTargetClient, *, vm: str) -> dict[str, object]:
    raw = await client.request_read("get_vcenter_vm", path_parameters={"vm": vm})
    if not isinstance(raw, dict):
        raise UpstreamProtocolError(
            "vCenter VM detail was not an object", target_id=client.target_id
        )
    allowed = ("name", "power_state", "guest_OS", "cpu", "memory", "hardware")
    return {key: raw[key] for key in allowed if key in raw}


async def list_vcenter_hosts(
    client: VcenterTargetClient,
    *,
    names: Sequence[str] | None = None,
    connection_states: Sequence[str] | None = None,
    hosts: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
    clusters: Sequence[str] | None = None,
    standalone: bool | None = None,
) -> dict[str, object]:
    raw = await client.request_read(
        "list_vcenter_hosts",
        query={
            "names": names,
            "connection_states": connection_states,
            "hosts": hosts,
            "datacenters": datacenters,
            "clusters": clusters,
            "standalone": standalone,
        },
    )
    if not isinstance(raw, list):
        raise UpstreamProtocolError(
            "vCenter host list was not a list", target_id=client.target_id
        )
    client.enforce_list_cap(len(raw))
    allowed = ("host", "name", "connection_state", "power_state")
    projected = [
        {key: item[key] for key in allowed if key in item}
        for item in raw
        if isinstance(item, dict)
    ]
    return {"items": projected, "count": len(projected)}


async def get_vcenter_session(client: VcenterTargetClient) -> dict[str, object]:
    raw = await client.request_read("get_vcenter_session")
    if not isinstance(raw, dict):
        raise UpstreamProtocolError(
            "vCenter session detail was not an object", target_id=client.target_id
        )
    allowed = ("user", "created_time", "last_accessed_time")
    return {key: raw[key] for key in allowed if key in raw}


HANDLERS = {
    "list_vcenter_vms": list_vcenter_vms,
    "get_vcenter_vm": get_vcenter_vm,
    "list_vcenter_hosts": list_vcenter_hosts,
    "get_vcenter_session": get_vcenter_session,
}


def _render_pack_path(tool: PackTool, values: Mapping[str, str]) -> str:
    rendered = tool.path
    expected: set[str] = set()
    for segment in tool.path.split("{")[1:]:
        expected.add(segment.split("}", 1)[0])
    if set(values) != expected:
        raise ValueError("path parameters do not match the backend pack")
    for name, value in values.items():
        if not _SAFE_PATH_VALUE.fullmatch(value):
            raise ValueError(f"unsafe path identifier {name!r}")
        rendered = rendered.replace("{" + name + "}", value)
    return rendered


def _check_pack_query(
    tool: PackTool, values: Mapping[str, object]
) -> dict[str, object]:
    unknown = set(values) - set(tool.query)
    if unknown:
        raise ValueError(
            f"query parameters are not declared by the pack: {sorted(unknown)}"
        )
    return {key: value for key, value in values.items() if value is not None}


def _decode_json(response: httpx.Response, target_id: TargetId) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamProtocolError(
            "vCenter returned a non-JSON success response", target_id=target_id
        ) from exc


def _rebuffered_headers(headers: httpx.Headers) -> httpx.Headers:
    rebuilt = httpx.Headers(headers)
    rebuilt.pop("content-length", None)
    rebuilt.pop("content-encoding", None)
    return rebuilt


def _project_vm_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    allowed = ("vm", "name", "power_state", "cpu_count", "memory_size_MiB")
    return {key: value[key] for key in allowed if key in value}
