"""Static runtime for read tools declared by validated backend packs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from vcf_mcp.backend_packs import BackendPack, PackTool
from vcf_mcp.contracts import (
    ConfigurationGeneration,
    HttpMethod,
    TargetId,
    TargetRecord,
)
from vcf_mcp.vcf.caps import MAX_UPSTREAM_RESPONSE_BYTES
from vcf_mcp.vcf.client import (
    TOKEN_RELEASE_TIMEOUT,
    TargetCredentials,
    build_tls_verifier,
)
from vcf_mcp.vcf.errors import (
    AuthenticationError,
    PermissionDeniedError,
    ReauthenticationExhausted,
    ResultCapExceeded,
    TargetConfigurationSuperseded,
    UpstreamProtocolError,
    UpstreamStatusError,
    UpstreamUnavailableError,
)
from vcf_mcp.vcf.outbound import _SAFE_PATH_VALUE
from vcf_mcp.upstream_control import UpstreamControl


DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=60, write=30, pool=10)
DEFAULT_MAX_LIST_ITEMS = 4_000
MAX_REAUTHENTICATIONS_PER_REQUEST = 1
OPS_TOKEN_RELEASE_PATH = "/suite-api/api/auth/token/release"


class DeclaredBackendClient:
    """Execute one frozen pack without binding requests to generated clients."""

    def __init__(
        self,
        *,
        target: TargetRecord,
        credentials: TargetCredentials,
        pack: BackendPack,
        root_ca_pem: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        upstream_control: UpstreamControl | None = None,
    ) -> None:
        self._target = target
        self._credentials = credentials
        self._pack = pack
        self._tools = {tool.name: tool for tool in pack.tools}
        self._http = http_client or httpx.AsyncClient(
            base_url=f"https://{target.fqdn}",
            verify=build_tls_verifier(target, root_ca_pem),
            timeout=DEFAULT_TIMEOUT,
        )
        self._max_response_bytes = int(
            pack.caps.get("max_response_bytes", MAX_UPSTREAM_RESPONSE_BYTES)
        )
        self._max_list_items = int(
            pack.caps.get("max_list_items", DEFAULT_MAX_LIST_ITEMS)
        )
        self._auth_value: str | None = None
        self._auth_generation = 0
        self._auth_lock = asyncio.Lock()
        self._closed = False
        self._inflight: set[asyncio.Task[object]] = set()
        self._upstream_control = upstream_control or UpstreamControl(
            backend_name=pack.backend.value,
            target_id=str(target.id),
            max_concurrency=int(pack.caps.get("max_concurrency", 8)),
            max_429_retries=int(pack.caps.get("max_429_retries", 3)),
        )

    @property
    def target_id(self) -> TargetId:
        return self._target.id

    @property
    def configuration_generation(self) -> ConfigurationGeneration:
        return self._target.configuration_generation

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def request_declared(
        self,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> dict[str, object]:
        if self._closed:
            raise TargetConfigurationSuperseded(
                "the target configuration was replaced",
                target_id=self._target.id,
            )
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"tool {tool_name!r} is not in the backend pack")
        path, query, body = _render_request(self._pack, tool, arguments)
        task = asyncio.current_task()
        await self._upstream_control.acquire()
        if task is not None:
            self._inflight.add(task)
        try:
            reauthentications = 0
            rate_limit_attempts = 0
            while True:
                headers, auth, generation = await self._authorization()
                response = await self._send(
                    tool.method,
                    path,
                    query=query,
                    body=body,
                    headers=headers,
                    auth=auth,
                )
                if response.status_code == 429 and await self._upstream_control.backoff_for_429(
                    attempt=rate_limit_attempts,
                    retry_after=response.headers.get("retry-after"),
                ):
                    rate_limit_attempts += 1
                    continue
                if response.status_code == 401:
                    if not _reauthenticates(self._pack.auth_scheme):
                        raise AuthenticationError(
                            f"{self._pack.product} refused these credentials",
                            target_id=self._target.id,
                        )
                    if reauthentications >= MAX_REAUTHENTICATIONS_PER_REQUEST:
                        raise ReauthenticationExhausted(
                            f"a new {self._pack.product} session was refused",
                            target_id=self._target.id,
                        )
                    reauthentications += 1
                    self._refuse_if_superseded()
                    await self._reacquire(generation)
                    continue
                if response.status_code == 403:
                    raise PermissionDeniedError(
                        f"{self._pack.product} refused this read for the credential's role",
                        target_id=self._target.id,
                        path=path,
                    )
                if response.status_code >= 400:
                    raise UpstreamStatusError(
                        f"{self._pack.product} answered {response.status_code} for this read",
                        status_code=response.status_code,
                        target_id=self._target.id,
                        path=path,
                    )
                decoded = _decode_json(response, self._target.id, self._pack.product)
                self._refuse_if_superseded()
                return _project_response(
                    decoded,
                    allowed_keys=tool.response_keys,
                    max_list_items=self._max_list_items,
                    target_id=self._target.id,
                )
        finally:
            if task is not None:
                self._inflight.discard(task)
            self._upstream_control.release()

    async def _authorization(
        self,
    ) -> tuple[dict[str, str], httpx.BasicAuth | None, int]:
        scheme = self._pack.auth_scheme
        if scheme == "basic":
            username, password = self._credentials.basic_auth_tuple()
            return {}, httpx.BasicAuth(username, password), 0
        if scheme == "bearer_token":
            _, token = self._credentials.basic_auth_tuple()
            return {"Authorization": f"Bearer {token}"}, None, 0
        value, generation = await self._session()
        if scheme == "vcenter_session":
            return {"vmware-api-session-id": value}, None, generation
        if scheme == "ops_exchange":
            return {"X-JWT-Token": value}, None, generation
        if scheme == "ops_token":
            return {"Authorization": f"OpsToken {value}"}, None, generation
        return {"Authorization": f"Bearer {value}"}, None, generation

    async def _session(self) -> tuple[str, int]:
        if self._auth_value is not None:
            return self._auth_value, self._auth_generation
        async with self._auth_lock:
            if self._auth_value is None:
                await self._acquire_locked()
            assert self._auth_value is not None
            return self._auth_value, self._auth_generation

    async def _reacquire(self, observed_generation: int) -> None:
        async with self._auth_lock:
            if self._auth_generation != observed_generation:
                return
            previous = self._auth_value
            self._auth_value = None
            if previous and self._pack.auth_scheme == "ops_bearer":
                await self._release_ops_bearer(previous)
            await self._acquire_locked()

    async def _release_ops_bearer(self, token: str) -> None:
        try:
            await self._http.post(
                OPS_TOKEN_RELEASE_PATH,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"OpsToken {token}",
                },
                timeout=TOKEN_RELEASE_TIMEOUT,
            )
        except httpx.HTTPError:
            pass

    async def _acquire_locked(self) -> None:
        scheme = self._pack.auth_scheme
        username, password = self._credentials.basic_auth_tuple()

        async def acquire_response() -> httpx.Response:
            if scheme == "vcenter_session":
                return await self._http.post(
                    "/api/session",
                    auth=httpx.BasicAuth(username, password),
                    headers={"Accept": "application/json"},
                )
            if scheme == "sddc_token":
                return await self._http.post(
                    "/v1/tokens",
                    json={"username": username, "password": password},
                    headers={"Accept": "application/json"},
                )
            return await self._http.post(
                "/suite-api/api/auth/token/acquire",
                json=self._credentials.acquire_payload(),
                headers={"Accept": "application/json"},
            )

        response = await self._auth_response_with_backoff(acquire_response)
        if response.status_code == 401:
            raise AuthenticationError(
                f"{self._pack.product} refused these credentials",
                target_id=self._target.id,
            )
        if response.status_code >= 400:
            raise UpstreamStatusError(
                f"{self._pack.product} authentication answered {response.status_code}",
                status_code=response.status_code,
                target_id=self._target.id,
                path=response.request.url.path,
            )
        decoded = _decode_json(response, self._target.id, self._pack.product)
        if scheme == "ops_exchange":
            ops_token = _token_from(decoded)

            async def exchange_response() -> httpx.Response:
                return await self._http.post(
                    "/suite-api/api/auth/token/exchange",
                    json={"serviceKeys": ["ops-li"]},
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"OpsToken {ops_token}",
                    },
                )

            response = await self._auth_response_with_backoff(exchange_response)
            if response.status_code >= 400:
                raise UpstreamStatusError(
                    f"{self._pack.product} token exchange answered {response.status_code}",
                    status_code=response.status_code,
                    target_id=self._target.id,
                    path=response.request.url.path,
                )
            decoded = _decode_json(response, self._target.id, self._pack.product)
        self._auth_value = _token_from(decoded)
        self._auth_generation += 1

    async def _auth_response_with_backoff(
        self, send: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await send()
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"{self._pack.product} could not be reached ({type(exc).__name__})",
                    target_id=self._target.id,
                ) from None
            if response.status_code != 429 or not await self._upstream_control.backoff_for_429(
                attempt=attempt,
                retry_after=response.headers.get("Retry-After"),
            ):
                return response
            attempt += 1

    async def _send(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, object],
        body: object | None,
        headers: Mapping[str, str],
        auth: httpx.BasicAuth | None,
    ) -> httpx.Response:
        try:
            request = self._http.build_request(
                method.value,
                path,
                params=query or None,
                json=body,
                headers={"Accept": "application/json", **headers},
            )
            if auth is not None:
                request = next(auth.sync_auth_flow(request))
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"{self._pack.product} could not be reached ({type(exc).__name__})",
                target_id=self._target.id,
            ) from None
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
        finally:
            await response.aclose()
        rebuilt_headers = httpx.Headers(response.headers)
        rebuilt_headers.pop("content-length", None)
        rebuilt_headers.pop("content-encoding", None)
        return httpx.Response(
            status_code=response.status_code,
            headers=rebuilt_headers,
            content=bytes(buffered),
            request=request,
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
        session = self._auth_value
        self._auth_value = None
        if session and self._pack.auth_scheme == "vcenter_session":
            try:
                await self._http.delete(
                    "/api/session", headers={"vmware-api-session-id": session}
                )
            except httpx.HTTPError:
                pass
        elif session and self._pack.auth_scheme == "ops_bearer":
            try:
                await self._release_ops_bearer(session)
            except asyncio.CancelledError:
                pass
        await self._http.aclose()


def handlers_for_pack(pack: BackendPack) -> dict[str, Any]:
    handlers: dict[str, Any] = {}
    for tool in pack.tools:

        async def handler(
            client: DeclaredBackendClient,
            *,
            _tool_name: str = tool.name,
            **arguments: object,
        ) -> dict[str, object]:
            return await client.request_declared(_tool_name, arguments)

        handlers[tool.name] = handler
    return handlers


def _render_request(
    pack: BackendPack,
    tool: PackTool,
    arguments: Mapping[str, object],
) -> tuple[str, dict[str, object], object | None]:
    expected = {argument.name for argument in tool.arguments}
    if set(arguments) - expected:
        raise ValueError("arguments do not match the frozen backend tool schema")
    path = tool.path
    query = dict(tool.fixed_query)
    direct_body: dict[str, object] = {}
    for argument in tool.arguments:
        if argument.required and argument.name not in arguments:
            raise ValueError(f"required argument {argument.name!r} is missing")
        value = arguments.get(argument.name, argument.default)
        wire_name = str(argument.wire_name)
        if argument.location == "path":
            rendered = str(value)
            if not _SAFE_PATH_VALUE.fullmatch(rendered):
                raise ValueError(f"unsafe path identifier {argument.name!r}")
            path = path.replace("{" + wire_name + "}", rendered)
        elif argument.location == "query" and value is not None:
            query[wire_name] = value
        elif argument.location == "body" and value is not None:
            direct_body[wire_name] = value
    if set(query) - set(tool.query):
        raise ValueError("query parameters exceed the frozen outbound contract")
    if tool.body_template is not None:
        expanded_arguments = {
            argument.name: arguments.get(argument.name, argument.default)
            for argument in tool.arguments
        }
        body = _render_template(tool.body_template, expanded_arguments)
    elif direct_body:
        body = direct_body
    else:
        body = None
    if isinstance(body, dict) and set(body) - set(tool.body):
        raise ValueError("body keys exceed the frozen outbound contract")
    full_path = f"{pack.api_root}{path}" or "/"
    return full_path, query, body


def _render_template(value: object, arguments: Mapping[str, object]) -> object:
    if isinstance(value, dict):
        marker = value.get("$argument")
        if marker is not None and len(value) == 1:
            return arguments[str(marker)]
        return {
            str(key): rendered
            for key, nested in value.items()
            if (rendered := _render_template(nested, arguments)) is not None
        }
    if isinstance(value, list):
        return [_render_template(nested, arguments) for nested in value]
    return value


def _project_response(
    value: object,
    *,
    allowed_keys: frozenset[str],
    max_list_items: int,
    target_id: TargetId,
) -> dict[str, object]:
    if isinstance(value, list):
        if len(value) > max_list_items:
            raise ResultCapExceeded(
                cap_name="max_list_items",
                cap_value=max_list_items,
                requested=len(value),
                unit="items",
                target_id=target_id,
            )
        return {
            "items": [
                _project_value(
                    item,
                    allowed_keys,
                    max_list_items=max_list_items,
                    target_id=target_id,
                )
                for item in value
            ],
            "count": len(value),
        }
    if not isinstance(value, dict):
        return {"value": value} if "value" in allowed_keys else {}
    return _project_value(
        value,
        allowed_keys,
        max_list_items=max_list_items,
        target_id=target_id,
    )


def _project_value(
    value: object,
    allowed_keys: frozenset[str],
    *,
    max_list_items: int,
    target_id: TargetId,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _project_value(
                nested,
                allowed_keys,
                max_list_items=max_list_items,
                target_id=target_id,
            )
            for key, nested in value.items()
            if str(key) in allowed_keys
        }
    if isinstance(value, list):
        if len(value) > max_list_items:
            raise ResultCapExceeded(
                cap_name="max_list_items",
                cap_value=max_list_items,
                requested=len(value),
                unit="items",
                target_id=target_id,
            )
        return [
            _project_value(
                item,
                allowed_keys,
                max_list_items=max_list_items,
                target_id=target_id,
            )
            for item in value
        ]
    return value


def _token_from(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        for key in ("token", "accessToken", "access_token", "jwt"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    raise UpstreamProtocolError("authentication returned no token")


def _decode_json(
    response: httpx.Response,
    target_id: TargetId,
    product: str,
) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamProtocolError(
            f"{product} returned a non-JSON response",
            target_id=target_id,
        ) from exc


def _reauthenticates(scheme: str) -> bool:
    return scheme in {
        "ops_bearer",
        "ops_exchange",
        "ops_token",
        "sddc_token",
        "vcenter_session",
    }
