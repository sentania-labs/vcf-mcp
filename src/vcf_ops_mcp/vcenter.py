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
    return await _list_projected(
        client,
        "list_vcenter_vms",
        query={
            "vms": vms,
            "names": names,
            "folders": folders,
            "datacenters": datacenters,
            "hosts": hosts,
            "clusters": clusters,
            "resource_pools": resource_pools,
            "power_states": power_states,
        },
        allowed=("vm", "name", "power_state", "cpu_count", "memory_size_mib"),
        label="VM",
    )


async def get_vcenter_vm(client: VcenterTargetClient, *, vm: str) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_vm",
        path_parameters={"vm": vm},
        allowed=(
            "name",
            "guest_os",
            "identity",
            "power_state",
            "hardware",
            "boot",
            "cpu",
            "memory",
        ),
        label="VM",
    )


async def list_vcenter_hosts(
    client: VcenterTargetClient,
    *,
    hosts: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
    clusters: Sequence[str] | None = None,
    connection_states: Sequence[str] | None = None,
    host_uuids: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_hosts",
        query={
            "hosts": hosts,
            "names": names,
            "folders": folders,
            "datacenters": datacenters,
            "clusters": clusters,
            "connection_states": connection_states,
            "host_uuids": host_uuids,
        },
        allowed=("host", "name", "connection_state", "power_state", "host_uuid"),
        label="host",
    )


async def list_vcenter_clusters(
    client: VcenterTargetClient,
    *,
    clusters: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_clusters",
        query={
            "clusters": clusters,
            "names": names,
            "folders": folders,
            "datacenters": datacenters,
        },
        allowed=("cluster", "name", "ha_enabled", "drs_enabled"),
        label="cluster",
    )


async def get_vcenter_cluster(
    client: VcenterTargetClient, *, cluster: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_cluster",
        path_parameters={"cluster": cluster},
        allowed=("name", "resource_pool"),
        label="cluster",
    )


async def list_vcenter_datacenters(
    client: VcenterTargetClient,
    *,
    datacenters: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_datacenters",
        query={"datacenters": datacenters, "names": names, "folders": folders},
        allowed=("datacenter", "name"),
        label="datacenter",
    )


async def get_vcenter_datacenter(
    client: VcenterTargetClient, *, datacenter: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_datacenter",
        path_parameters={"datacenter": datacenter},
        allowed=(
            "name",
            "datastore_folder",
            "host_folder",
            "network_folder",
            "vm_folder",
        ),
        label="datacenter",
    )


async def list_vcenter_datastores(
    client: VcenterTargetClient,
    *,
    datastores: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    types: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_datastores",
        query={
            "datastores": datastores,
            "names": names,
            "types": types,
            "folders": folders,
            "datacenters": datacenters,
        },
        allowed=("datastore", "name", "type", "free_space", "capacity"),
        label="datastore",
    )


async def get_vcenter_datastore(
    client: VcenterTargetClient, *, datastore: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_datastore",
        path_parameters={"datastore": datastore},
        allowed=(
            "name",
            "type",
            "accessible",
            "free_space",
            "multiple_host_access",
            "thin_provisioning_supported",
        ),
        label="datastore",
    )


async def list_vcenter_resource_pools(
    client: VcenterTargetClient,
    *,
    resource_pools: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    parent_resource_pools: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
    hosts: Sequence[str] | None = None,
    clusters: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_resource_pools",
        query={
            "resource_pools": resource_pools,
            "names": names,
            "parent_resource_pools": parent_resource_pools,
            "datacenters": datacenters,
            "hosts": hosts,
            "clusters": clusters,
        },
        allowed=("resource_pool", "name"),
        label="resource pool",
    )


async def get_vcenter_resource_pool(
    client: VcenterTargetClient, *, resource_pool: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_resource_pool",
        path_parameters={"resourcePool": resource_pool},
        allowed=("name", "resource_pools", "cpu_allocation", "memory_allocation"),
        label="resource pool",
    )


async def list_vcenter_folders(
    client: VcenterTargetClient,
    *,
    folders: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    parent_folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_folders",
        query={
            "folders": folders,
            "names": names,
            "parent_folders": parent_folders,
            "datacenters": datacenters,
        },
        allowed=("folder", "name", "type"),
        label="folder",
    )


async def list_vcenter_networks(
    client: VcenterTargetClient,
    *,
    networks: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    types: Sequence[str] | None = None,
    folders: Sequence[str] | None = None,
    datacenters: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_networks",
        query={
            "networks": networks,
            "names": names,
            "types": types,
            "folders": folders,
            "datacenters": datacenters,
        },
        allowed=("network", "name", "type"),
        label="network",
    )


async def list_vcenter_storage_policies(
    client: VcenterTargetClient,
    *,
    policies: Sequence[str] | None = None,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_storage_policies",
        query={"policies": policies},
        allowed=("policy", "name", "description"),
        label="storage policy",
    )


async def list_vcenter_content_libraries(
    client: VcenterTargetClient,
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_content_libraries",
        allowed=("library",),
        identifier_key="library",
        label="content library",
    )


async def get_vcenter_content_library(
    client: VcenterTargetClient, *, library_id: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_content_library",
        path_parameters={"libraryId": library_id},
        allowed=(
            "id",
            "name",
            "description",
            "type",
            "creation_time",
            "last_modified_time",
            "last_sync_time",
            "version",
        ),
        label="content library",
    )


async def list_vcenter_content_library_items(
    client: VcenterTargetClient, *, library_id: str
) -> dict[str, object]:
    return await _list_projected(
        client,
        "list_vcenter_content_library_items",
        query={"library_id": library_id},
        allowed=("library_item",),
        identifier_key="library_item",
        label="content library item",
    )


async def get_vcenter_content_library_item(
    client: VcenterTargetClient, *, library_item_id: str
) -> dict[str, object]:
    return await _get_projected(
        client,
        "get_vcenter_content_library_item",
        path_parameters={"libraryItemId": library_item_id},
        allowed=(
            "id",
            "library_id",
            "name",
            "description",
            "type",
            "content_version",
            "creation_time",
            "last_modified_time",
            "last_sync_time",
            "metadata_version",
            "cached",
            "size",
            "version",
        ),
        label="content library item",
    )


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
    "list_vcenter_clusters": list_vcenter_clusters,
    "get_vcenter_cluster": get_vcenter_cluster,
    "list_vcenter_datacenters": list_vcenter_datacenters,
    "get_vcenter_datacenter": get_vcenter_datacenter,
    "list_vcenter_datastores": list_vcenter_datastores,
    "get_vcenter_datastore": get_vcenter_datastore,
    "list_vcenter_resource_pools": list_vcenter_resource_pools,
    "get_vcenter_resource_pool": get_vcenter_resource_pool,
    "list_vcenter_folders": list_vcenter_folders,
    "list_vcenter_networks": list_vcenter_networks,
    "list_vcenter_storage_policies": list_vcenter_storage_policies,
    "list_vcenter_content_libraries": list_vcenter_content_libraries,
    "get_vcenter_content_library": get_vcenter_content_library,
    "list_vcenter_content_library_items": list_vcenter_content_library_items,
    "get_vcenter_content_library_item": get_vcenter_content_library_item,
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


async def _list_projected(
    client: VcenterTargetClient,
    tool_name: str,
    *,
    allowed: Sequence[str],
    label: str,
    query: Mapping[str, object] | None = None,
    identifier_key: str | None = None,
) -> dict[str, object]:
    raw = await client.request_read(tool_name, query=query)
    if not isinstance(raw, list):
        raise UpstreamProtocolError(
            f"vCenter {label} list was not a list", target_id=client.target_id
        )
    client.enforce_list_cap(len(raw))
    projected: list[dict[str, object]] = []
    for item in raw:
        if identifier_key is not None and isinstance(item, str):
            projected.append({identifier_key: item})
            continue
        if not isinstance(item, dict):
            raise UpstreamProtocolError(
                f"vCenter {label} list contained a non-object",
                target_id=client.target_id,
            )
        projected.append({key: item[key] for key in allowed if key in item})
    return {"items": projected, "count": len(projected)}


async def _get_projected(
    client: VcenterTargetClient,
    tool_name: str,
    *,
    path_parameters: Mapping[str, str],
    allowed: Sequence[str],
    label: str,
) -> dict[str, object]:
    raw = await client.request_read(tool_name, path_parameters=path_parameters)
    if not isinstance(raw, dict):
        raise UpstreamProtocolError(
            f"vCenter {label} detail was not an object", target_id=client.target_id
        )
    return {key: raw[key] for key in allowed if key in raw}
