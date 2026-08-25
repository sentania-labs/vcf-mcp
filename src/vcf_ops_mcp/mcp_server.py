"""Endpoint-per-backend MCP composition through the mandatory dispatcher."""

from __future__ import annotations

import asyncio
import inspect
import re
import shutil
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from vcf_ops_mcp.audit import SqliteAuditRepository
from vcf_ops_mcp.backend_packs import (
    BackendPack,
    PackArgument,
    PackTool,
    load_backend_packs,
)
from vcf_ops_mcp.contracts import (
    BackendKind,
    Capability,
    CapabilityName,
    HttpMethod,
    InvalidationMode,
    InvalidationResult,
    OutboundContract,
    RequestIdentity,
    TargetConfigurationChange,
    TargetId,
    TargetRecord,
    TerminalState,
)
from vcf_ops_mcp.dispatcher import (
    DispatchDependencies,
    Dispatcher,
    DispatchError,
    ToolRegistry,
)
from vcf_ops_mcp.dispatcher.reservations import FreeSpaceReservations
from vcf_ops_mcp.runtime_repository import RuntimeRepository
from vcf_ops_mcp.skills import SkillCatalog
from vcf_ops_mcp.vcenter import HANDLERS as VCENTER_HANDLERS
from vcf_ops_mcp.vcenter import VcenterTargetClient
from vcf_ops_mcp.vcf.adapters import ADAPTERS_BY_TOOL_NAME, READ_ADAPTERS
from vcf_ops_mcp.vcf.client import TargetCredentials, VcfTargetClient
from vcf_ops_mcp.vcf.outbound import OutboundAllowlist


DEFAULT_TOOL_DEADLINE_SECONDS = 75.0
CALLER_HEADER = "x-vcf-caller-id"
_CALLER_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")


class ApiKeyTokenVerifier:
    """Resolve opaque keys on every request and enforce endpoint scope."""

    def __init__(self, repository: RuntimeRepository, endpoint: str) -> None:
        self._repository = repository
        self._endpoint = endpoint

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = await self._repository.resolve_request_identity(token)
        if (
            identity is None
            or identity.revoked
            or self._endpoint not in identity.allowed_endpoints
        ):
            return None
        return AccessToken(
            token=token,
            client_id=str(identity.key_id),
            scopes=sorted(str(scope) for scope in identity.granted_scopes),
            claims={
                "allowed_targets": sorted(
                    str(target_id) for target_id in identity.allowed_targets
                ),
                "allowed_endpoints": sorted(identity.allowed_endpoints),
            },
        )


class BackendClientPool:
    """Cache clients by target generation and implement edit invalidation."""

    def __init__(
        self,
        repository: RuntimeRepository,
        pack: BackendPack,
        *,
        client_factory: Callable[..., object] | None = None,
    ) -> None:
        self._repository = repository
        self._pack = pack
        self._client_factory = client_factory
        self._factory_accepts_root_ca = bool(
            client_factory is not None and _accepts_root_ca(client_factory)
        )
        self._clients: dict[TargetId, object] = {}
        self._lock = asyncio.Lock()

    async def get(self, target: TargetRecord) -> object:
        if target.backend is not self._pack.backend:
            raise PermissionError("target belongs to another backend")
        async with self._lock:
            existing = self._clients.get(target.id)
            if (
                existing is not None
                and existing.configuration_generation == target.configuration_generation
                and not existing.is_closed
            ):
                return existing
            if existing is not None:
                existing.mark_closed()
                await existing.aclose()
            credentials = await self._repository.get_credentials(target.id)
            root_ca = await self._repository.get_root_ca(target.id)
            client = self._build_client(target, credentials, root_ca)
            self._clients[target.id] = client
            return client

    def _build_client(
        self,
        target: TargetRecord,
        credentials: TargetCredentials,
        root_ca: str | None,
    ) -> object:
        if self._client_factory is not None:
            if self._factory_accepts_root_ca:
                return self._client_factory(target, credentials, root_ca)
            return self._client_factory(target, credentials)
        if self._pack.backend is BackendKind.OPS:
            allowlist = _ops_allowlist(self._pack)
            return VcfTargetClient(
                target=target,
                credentials=credentials,
                allowlist=allowlist,
                root_ca_pem=root_ca,
            )
        tools = {tool.name: tool for tool in self._pack.tools}
        return VcenterTargetClient(
            target=target,
            credentials=credentials,
            tools=tools,
            root_ca_pem=root_ca,
        )

    async def invalidate(
        self,
        change: TargetConfigurationChange,
        *,
        mode: InvalidationMode,
    ) -> InvalidationResult:
        async with self._lock:
            client = self._clients.get(change.target_id)
            if client is None:
                return InvalidationResult(change, mode, 0, 0)
            if client.configuration_generation != change.previous_generation:
                raise RuntimeError("live client generation does not match edit")
            inflight = client.mark_closed()
        if mode is InvalidationMode.CANCEL:
            cancelled = await client.cancel()
            drained = 0
        else:
            await client.drain()
            drained = inflight
            cancelled = 0
        async with self._lock:
            self._clients.pop(change.target_id, None)
        await client.aclose()
        return InvalidationResult(change, mode, drained, cancelled)

    async def aclose(self) -> None:
        async with self._lock:
            clients = tuple(self._clients.values())
            self._clients.clear()
        for client in clients:
            client.mark_closed()
            await client.aclose()


class CompositeInvalidator:
    """Fan one target edit out to every startup-frozen endpoint pool."""

    def __init__(self, pools: tuple[BackendClientPool, ...]) -> None:
        self._pools = pools

    async def invalidate(
        self,
        change: TargetConfigurationChange,
        *,
        mode: InvalidationMode,
    ) -> InvalidationResult:
        results = [await pool.invalidate(change, mode=mode) for pool in self._pools]
        return InvalidationResult(
            change,
            mode,
            sum(result.drained_requests for result in results),
            sum(result.cancelled_requests for result in results),
        )


@dataclass(frozen=True, slots=True)
class McpSurface:
    endpoint: str
    app: Starlette
    tool_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class McpSurfaces:
    by_endpoint: Mapping[str, McpSurface]
    invalidator: CompositeInvalidator


def build_mcp_surfaces(
    *,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    skills: SkillCatalog,
    digest_key: bytes,
    public_base_url: str,
    client_factories: Mapping[BackendKind, Callable[..., object]] | None = None,
) -> McpSurfaces:
    """Enumerate registered backends and freeze one tool surface per backend."""

    packs = load_backend_packs()
    targets = runtime_repository.list_at_startup()
    wired = frozenset(target.backend for target in targets)
    pools: list[BackendClientPool] = []
    surfaces: dict[str, McpSurface] = {}
    for backend in sorted(wired, key=lambda value: value.value):
        pack = packs[backend]
        pool = BackendClientPool(
            runtime_repository,
            pack,
            client_factory=(client_factories or {}).get(backend),
        )
        pools.append(pool)
        surfaces[backend.value] = _build_backend_surface(
            runtime_repository=runtime_repository,
            audit_repository=audit_repository,
            digest_key=digest_key,
            public_base_url=public_base_url,
            pack=pack,
            pool=pool,
        )
    surfaces["vcf"] = _build_management_surface(
        runtime_repository=runtime_repository,
        audit_repository=audit_repository,
        skills=skills,
        digest_key=digest_key,
        public_base_url=public_base_url,
        packs=packs,
        wired=wired,
    )
    return McpSurfaces(surfaces, CompositeInvalidator(tuple(pools)))


def build_mcp_surface(
    *,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    skills: SkillCatalog,
    digest_key: bytes,
    public_base_url: str,
    client_factory: Callable[..., object] | None = None,
) -> McpSurface:
    """Compatibility builder for tests that exercise the Operations endpoint."""

    pack = load_backend_packs()[BackendKind.OPS]
    pool = BackendClientPool(runtime_repository, pack, client_factory=client_factory)
    return _build_backend_surface(
        runtime_repository=runtime_repository,
        audit_repository=audit_repository,
        digest_key=digest_key,
        public_base_url=public_base_url,
        pack=pack,
        pool=pool,
    )


def _build_backend_surface(
    *,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    digest_key: bytes,
    public_base_url: str,
    pack: BackendPack,
    pool: BackendClientPool,
) -> McpSurface:
    mcp = _new_mcp(
        product=f"Sentania {pack.product} MCP (unofficial)",
        endpoint=pack.endpoint,
        public_base_url=public_base_url,
        verifier=ApiKeyTokenVerifier(runtime_repository, pack.endpoint),
        close=pool.aclose,
    )
    registry = ToolRegistry()
    handlers = _handlers_for_pack(pack)
    for tool in pack.tools:
        selected_handler = handlers[tool.name]

        async def audited_handler(
            target: TargetRecord,
            arguments: Mapping[str, object],
            *,
            handler=selected_handler,
        ) -> Mapping[str, object]:
            client = await pool.get(target)
            return await handler(client, **dict(arguments))

        registry.register(_pack_registration(tool, pack, audited_handler))
    registry.freeze()
    dispatcher = _dispatcher(
        registry,
        runtime_repository,
        audit_repository,
        digest_key,
        endpoint=pack.endpoint,
        pack=pack,
    )
    for tool in pack.tools:
        function = _typed_tool_function(tool, dispatcher, pack.endpoint)
        mcp.tool(name=tool.name, description=tool.summary)(function)
    return McpSurface(
        endpoint=pack.endpoint,
        app=mcp.streamable_http_app(),
        tool_names=tuple(tool.name for tool in pack.tools),
    )


def _build_management_surface(
    *,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    skills: SkillCatalog,
    digest_key: bytes,
    public_base_url: str,
    packs: Mapping[BackendKind, BackendPack],
    wired: frozenset[BackendKind],
) -> McpSurface:
    endpoint = "vcf"
    mcp = _new_mcp(
        product="Sentania VCF MCP management (unofficial)",
        endpoint=endpoint,
        public_base_url=public_base_url,
        verifier=ApiKeyTokenVerifier(runtime_repository, endpoint),
    )
    registry = ToolRegistry()

    async def list_targets_handler(
        _target: TargetRecord, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        allowed = {str(value) for value in arguments["allowed_targets"]}
        endpoints = {str(value) for value in arguments["allowed_endpoints"]}
        targets = await runtime_repository.list()
        return {
            "targets": [
                _public_target(target)
                for target in targets
                if str(target.id) in allowed and target.backend.value in endpoints
            ]
        }

    async def wired_handler(
        _target: TargetRecord, _arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "backends": [
                {
                    "endpoint": f"/{kind.value}/mcp",
                    "backend": kind.value,
                    "product": packs[kind].product,
                    "tool_count": len(packs[kind].tools),
                    "pack_id": packs[kind].pack_id,
                    "pack_digest": packs[kind].digest,
                    "pack_version": packs[kind].version,
                    "unsigned": packs[kind].unsigned,
                }
                for kind in sorted(wired, key=lambda value: value.value)
            ]
        }

    async def access_handler(
        _target: TargetRecord, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "key_id": arguments["key_id"],
            "scopes": arguments["scopes"],
            "endpoints": arguments["allowed_endpoints"],
            "targets": arguments["allowed_targets"],
        }

    async def history_handler(
        _target: TargetRecord, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        records = await audit_repository.recent_records_for_caller(
            key_id=arguments["key_id"],
            caller_id=arguments.get("caller_id"),
            limit=int(arguments.get("limit", 50)),
        )
        return {
            "history": [
                {
                    "timestamp": record.timestamp.isoformat(),
                    "endpoint": record.endpoint_name,
                    "target_id": str(record.target_id),
                    "tool": record.tool_name,
                    "status": record.status.value,
                    "error_code": record.error_code,
                }
                for record in records
                if record.tool_name != "get_call_history"
            ],
            "caller_identity_present": bool(arguments.get("caller_id")),
        }

    async def health_handler(
        _target: TargetRecord, _arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "audit_writable": await audit_repository.is_writable(),
            "configuration_ready": await runtime_repository.is_ready(),
        }

    async def list_skills_handler(
        _target: TargetRecord, _arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {"skills": skills.list_skills()}

    async def get_skill_handler(
        _target: TargetRecord, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        version = arguments.get("version")
        skill = skills.get_skill(
            str(arguments.get("slug", "")),
            None if version is None else str(version),
        )
        if skill is None:
            raise KeyError("skill not found")
        return {
            "slug": skill.metadata.slug,
            "version": skill.metadata.version,
            "content": skill.content,
            "content_sha256": skill.metadata.content_sha256,
        }

    local = (
        ("list_targets", Capability.READ_TARGETS, "targets-v2", list_targets_handler),
        ("list_wired_backends", Capability.READ_TARGETS, "backends-v1", wired_handler),
        ("get_granted_access", Capability.READ_TARGETS, "access-v1", access_handler),
        ("get_call_history", Capability.READ_TARGETS, "history-v1", history_handler),
        ("get_server_health", Capability.READ_TARGETS, "health-v1", health_handler),
        ("list_skills", Capability.READ_SKILLS, "skills-index-v1", list_skills_handler),
        ("get_skill", Capability.READ_SKILLS, "skill-content-v1", get_skill_handler),
    )
    for name, capability, projection, handler in local:
        _register_local_tool(
            registry,
            name=name,
            capability=capability,
            projection=projection,
            handler=handler,
        )
    registry.freeze()
    dispatcher = _dispatcher(
        registry,
        runtime_repository,
        audit_repository,
        digest_key,
        endpoint=endpoint,
        enforce_endpoint_target=False,
    )

    async def dispatch_local(
        name: str, ctx: Context, arguments: Mapping[str, object]
    ) -> dict[str, Any]:
        identity = _identity_for_context(ctx)
        enriched = dict(arguments)
        enriched.update(
            {
                "key_id": identity.key_id,
                "scopes": sorted(str(value) for value in identity.granted_scopes),
                "allowed_targets": sorted(
                    str(value) for value in identity.allowed_targets
                ),
                "allowed_endpoints": sorted(identity.allowed_endpoints),
                "caller_id": identity.caller_id,
            }
        )
        return await _dispatch(
            dispatcher,
            name,
            ctx=ctx,
            target_id=_audit_anchor(identity),
            arguments=enriched,
        )

    @mcp.tool(name="list_targets", description="List targets this key can use.")
    async def list_targets(ctx: Context) -> dict[str, Any]:
        return await dispatch_local("list_targets", ctx, {})

    @mcp.tool(
        name="list_wired_backends", description="List startup-wired backend endpoints."
    )
    async def list_wired_backends(ctx: Context) -> dict[str, Any]:
        return await dispatch_local("list_wired_backends", ctx, {})

    @mcp.tool(
        name="get_granted_access",
        description="Show this key's endpoint and tool scopes.",
    )
    async def get_granted_access(ctx: Context) -> dict[str, Any]:
        return await dispatch_local("get_granted_access", ctx, {})

    @mcp.tool(
        name="get_call_history",
        description=(
            "Read this key and caller's recent history. Returns nothing when "
            f"the {CALLER_HEADER} header is absent."
        ),
    )
    async def get_call_history(ctx: Context, limit: int = 50) -> dict[str, Any]:
        return await dispatch_local("get_call_history", ctx, {"limit": limit})

    @mcp.tool(name="get_server_health", description="Read MCP persistence health.")
    async def get_server_health(ctx: Context) -> dict[str, Any]:
        return await dispatch_local("get_server_health", ctx, {})

    @mcp.tool(name="list_skills", description="List bundled operational skills.")
    async def list_skills(ctx: Context) -> dict[str, Any]:
        return await dispatch_local("list_skills", ctx, {})

    @mcp.tool(name="get_skill", description="Read one bundled operational skill.")
    async def get_skill(
        slug: str, ctx: Context, version: str | None = None
    ) -> dict[str, Any]:
        return await dispatch_local(
            "get_skill", ctx, {"slug": slug, "version": version}
        )

    def make_skill_reader(content: str):
        async def read_skill_resource() -> str:
            _require_scope(Capability.READ_SKILLS)
            return content

        return read_skill_resource

    for skill in skills.skills:
        reader = make_skill_reader(skill.content)
        mcp.resource(
            f"skill://{skill.metadata.slug}/{skill.metadata.version}",
            name=f"{skill.metadata.slug}@{skill.metadata.version}",
            description=skill.metadata.summary,
            mime_type="text/markdown",
        )(reader)
    for slug in skills.current:
        skill = skills.get_skill(slug)
        if skill is None:
            continue
        mcp.resource(
            f"skill://{slug}/current",
            name=f"{slug}@current",
            description=skill.metadata.summary,
            mime_type="text/markdown",
        )(make_skill_reader(skill.content))
        mcp.prompt(name=f"use_{slug}", description=skill.metadata.summary)(
            make_skill_reader(skill.content)
        )

    return McpSurface(
        endpoint=endpoint,
        app=mcp.streamable_http_app(),
        tool_names=tuple(spec.name for spec in registry),
    )


def implemented_scopes() -> frozenset[CapabilityName]:
    return frozenset(
        {
            *(adapter.capability for adapter in READ_ADAPTERS),
            Capability.READ_TARGETS,
            Capability.READ_SKILLS,
        }
    )


def _new_mcp(
    *,
    product: str,
    endpoint: str,
    public_base_url: str,
    verifier: ApiKeyTokenVerifier,
    close: Callable[[], object] | None = None,
) -> FastMCP:
    base = public_base_url.rstrip("/")
    public_url = urlsplit(base)
    if not public_url.scheme or not public_url.hostname:
        raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL")

    @asynccontextmanager
    async def lifespan(_server: FastMCP):
        try:
            yield
        finally:
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result

    return FastMCP(
        product,
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=f"{base}/{endpoint}/mcp",
            required_scopes=[],
        ),
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                public_url.netloc,
                f"{public_url.hostname}:*",
                "127.0.0.1:*",
                "localhost:*",
                "[::1]:*",
            ],
            allowed_origins=[
                f"{public_url.scheme}://{public_url.netloc}",
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ],
        ),
    )


def _handlers_for_pack(pack: BackendPack) -> Mapping[str, Callable[..., Any]]:
    if pack.backend is BackendKind.OPS:
        handlers = {
            name: adapter.handler for name, adapter in ADAPTERS_BY_TOOL_NAME.items()
        }
        for tool in pack.tools:
            adapter = ADAPTERS_BY_TOOL_NAME.get(tool.name)
            if adapter is None:
                raise ValueError(f"Operations pack has no handler for {tool.name}")
            contract = adapter.read_contract
            if (
                contract.contract.method is not tool.method
                or contract.contract.path_template != tool.path
                or contract.contract.permitted_query_parameters != tool.query
                or contract.permitted_body_keys != tool.body
                or adapter.projection_version != tool.projection
            ):
                raise ValueError(f"Operations pack contract drift for {tool.name}")
        return handlers
    if set(VCENTER_HANDLERS) != {tool.name for tool in pack.tools}:
        raise ValueError("vCenter handlers and pack tool definitions differ")
    return VCENTER_HANDLERS


def _accepts_root_ca(factory: Callable[..., object]) -> bool:
    parameters = inspect.signature(factory).parameters.values()
    return (
        any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )
        or len(tuple(parameters)) >= 3
    )


def _ops_allowlist(pack: BackendPack) -> OutboundAllowlist:
    contracts = [ADAPTERS_BY_TOOL_NAME[tool.name].read_contract for tool in pack.tools]
    return OutboundAllowlist(contracts)


def _pack_registration(
    tool: PackTool,
    pack: BackendPack,
    audited_handler: Callable[..., Any],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": tool.name,
        "capability": tool.capability,
        "key_scope": tool.capability,
        "target_policy": "target_required",
        "argument_digest_policy": "hmac_sha256_canonical_json",
        "projection": tool.projection,
        "outbound_contract": OutboundContract(tool.method, tool.path, tool.query),
        "audited_handler": audited_handler,
        "backend.pack_id": pack.pack_id,
        "backend.pack_digest": pack.digest,
        "backend.pack_version": pack.version,
        "backend.auth_scheme": pack.auth_scheme,
        "backend.permitted_body_keys": sorted(tool.body),
    }


def _typed_tool_function(
    tool: PackTool, dispatcher: Dispatcher, endpoint: str
) -> Callable[..., Any]:
    required = [argument for argument in tool.arguments if argument.required]
    optional = [argument for argument in tool.arguments if not argument.required]

    async def invoke(**kwargs: Any) -> dict[str, Any]:
        ctx = kwargs.pop("ctx")
        target_id = TargetId(kwargs.pop("target_id"))
        _identity_for_context(ctx)
        return await _dispatch(
            dispatcher,
            tool.name,
            ctx=ctx,
            target_id=target_id,
            arguments=kwargs,
        )

    result_type = dict[str, Any]
    annotations: dict[str, object] = {
        "target_id": str,
        "ctx": Context,
        "return": result_type,
    }
    parameters = [
        inspect.Parameter(
            "target_id",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
        )
    ]
    for argument in required:
        annotation = _argument_type(argument)
        annotations[argument.name] = annotation
        parameters.append(
            inspect.Parameter(
                argument.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation,
            )
        )
    parameters.append(
        inspect.Parameter(
            "ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Context
        )
    )
    for argument in optional:
        annotation = _argument_type(argument)
        annotations[argument.name] = annotation
        parameters.append(
            inspect.Parameter(
                argument.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation,
                default=argument.default,
            )
        )
    invoke.__name__ = tool.name
    invoke.__annotations__ = annotations
    invoke.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters, return_annotation=result_type
    )
    return invoke


def _argument_type(argument: PackArgument) -> object:
    types: dict[str, object] = {
        "str": str,
        "str?": str | None,
        "int": int,
        "int?": int | None,
        "bool": bool,
        "bool?": bool | None,
        "list[str]": list[str],
        "list[str]?": list[str] | None,
    }
    try:
        return types[argument.type]
    except KeyError as exc:
        raise ValueError(
            f"unsupported argument type {argument.type!r} in pack"
        ) from exc


def _register_local_tool(
    registry: ToolRegistry,
    *,
    name: str,
    capability: Capability,
    projection: str,
    handler: Callable[..., Any],
) -> None:
    registry.register(
        {
            "schema_version": 1,
            "name": name,
            "capability": capability,
            "key_scope": capability,
            "target_policy": "target_required",
            "argument_digest_policy": "hmac_sha256_canonical_json",
            "projection": projection,
            "outbound_contract": OutboundContract(
                HttpMethod.GET, f"/local/{name}", frozenset()
            ),
            "audited_handler": handler,
            "local.summary": "server-local read",
        }
    )


def _dispatcher(
    registry: ToolRegistry,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    digest_key: bytes,
    *,
    endpoint: str,
    pack: BackendPack | None = None,
    enforce_endpoint_target: bool = True,
) -> Dispatcher:
    reservations = FreeSpaceReservations(
        lambda: shutil.disk_usage(audit_repository.path.parent).free
    )
    return Dispatcher(
        registry,
        DispatchDependencies(
            targets=runtime_repository,
            audit=audit_repository,
            global_scopes=frozenset(spec.capability for spec in registry),
            digest_key=digest_key,
            reservations=reservations,
            endpoint_name=endpoint,
            enforce_endpoint_target=enforce_endpoint_target,
            pack_id=None if pack is None else pack.pack_id,
            pack_digest=None if pack is None else pack.digest,
            pack_version=None if pack is None else pack.version,
        ),
    )


def _identity_for_context(ctx: Context) -> RequestIdentity:
    token = get_access_token()
    if token is None or token.client_id is None:
        raise PermissionError("authenticated API key identity is unavailable")
    claims = token.claims or {}
    request = ctx.request_context.request
    if request is None:
        raise PermissionError("HTTP request context is unavailable")
    raw_caller = request.headers.get(CALLER_HEADER)
    caller_id = raw_caller if raw_caller and _CALLER_ID.fullmatch(raw_caller) else None
    identity = RequestIdentity(
        key_id=token.client_id,
        granted_scopes=frozenset(token.scopes),
        allowed_targets=frozenset(
            TargetId(str(value)) for value in claims.get("allowed_targets", [])
        ),
        allowed_endpoints=frozenset(
            str(value) for value in claims.get("allowed_endpoints", [])
        ),
        caller_id=caller_id,
    )
    request.state.identity = identity
    return identity


def _require_scope(capability: CapabilityName) -> None:
    token = get_access_token()
    if token is None or str(capability) not in token.scopes:
        raise PermissionError(f"API key requires scope {capability}")


def _audit_anchor(identity: RequestIdentity) -> TargetId:
    try:
        return min(identity.allowed_targets)
    except ValueError as exc:
        raise PermissionError("API key has no allowed target") from exc


async def _dispatch(
    dispatcher: Dispatcher,
    tool_name: str,
    *,
    ctx: Context,
    target_id: TargetId,
    arguments: Mapping[str, object],
) -> dict[str, Any]:
    try:
        result = await dispatcher.dispatch(
            tool_name,
            context=ctx,
            target_id=target_id,
            arguments=arguments,
            deadline_seconds=DEFAULT_TOOL_DEADLINE_SECONDS,
        )
    except DispatchError as exc:
        return {
            "state": TerminalState.DENIED.value,
            "error_code": exc.error_code,
            "message": str(exc),
        }
    body: dict[str, Any] = {"state": result.state.value}
    if result.state is TerminalState.OK:
        body["result"] = result.success
    else:
        body["error_code"] = result.error_code
        body["retryable"] = result.retryable
        if result.message:
            body["message"] = result.message
    return body


def _public_target(target: TargetRecord) -> dict[str, object]:
    return {
        "id": str(target.id),
        "name": target.name,
        "backend": target.backend.value,
        "endpoint": f"/{target.backend.value}/mcp",
        "fqdn": target.fqdn,
        "posture": target.posture.value,
        "is_prod": target.is_prod,
        "verify_ssl": target.verify_ssl,
        "has_custom_ca": target.has_custom_ca,
    }
