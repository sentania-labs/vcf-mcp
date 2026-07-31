"""Authenticated MCP surface assembled from the audited read-plane adapters."""

from __future__ import annotations

import asyncio
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
from vcf_ops_mcp.contracts import (
    Capability,
    CapabilityName,
    HttpMethod,
    OutboundContract,
    RequestIdentity,
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
from vcf_ops_mcp.vcf.adapters import READ_ADAPTERS, READ_ALLOWLIST
from vcf_ops_mcp.vcf.client import TargetCredentials, VcfTargetClient

DEFAULT_TOOL_DEADLINE_SECONDS = 75.0
LOCAL_TARGETS_TOOL = "list_targets"
LOCAL_SKILLS_TOOL = "list_skills"
LOCAL_SKILL_TOOL = "get_skill"


class ApiKeyTokenVerifier:
    """Resolve opaque API keys without caching revocation state."""

    def __init__(self, repository: RuntimeRepository) -> None:
        self._repository = repository

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = await self._repository.resolve_request_identity(token)
        if identity is None or identity.revoked:
            return None
        return AccessToken(
            token=token,
            client_id=str(identity.key_id),
            scopes=sorted(str(scope) for scope in identity.granted_scopes),
            claims={
                "allowed_targets": sorted(
                    str(target_id) for target_id in identity.allowed_targets
                )
            },
        )


class ReadClientPool:
    """Cache one authenticated VCF client per target generation."""

    def __init__(
        self,
        repository: RuntimeRepository,
        *,
        client_factory: Callable[
            [TargetRecord, TargetCredentials], VcfTargetClient
        ]
        | None = None,
    ) -> None:
        self._repository = repository
        self._client_factory = client_factory or self._default_client_factory
        self._clients: dict[TargetId, VcfTargetClient] = {}
        self._lock = asyncio.Lock()

    async def get(self, target: TargetRecord) -> VcfTargetClient:
        async with self._lock:
            existing = self._clients.get(target.id)
            if (
                existing is not None
                and existing.configuration_generation
                == target.configuration_generation
                and not existing.is_closed
            ):
                return existing
            if existing is not None:
                existing.mark_closed()
                await existing.aclose()
            credentials = await self._repository.get_credentials(target.id)
            client = self._client_factory(target, credentials)
            self._clients[target.id] = client
            return client

    async def aclose(self) -> None:
        async with self._lock:
            clients = tuple(self._clients.values())
            self._clients.clear()
        for client in clients:
            client.mark_closed()
            await client.aclose()

    @staticmethod
    def _default_client_factory(
        target: TargetRecord, credentials: TargetCredentials
    ) -> VcfTargetClient:
        return VcfTargetClient(
            target=target,
            credentials=credentials,
            allowlist=READ_ALLOWLIST,
        )


@dataclass(frozen=True, slots=True)
class McpSurface:
    app: Starlette
    tool_names: tuple[str, ...]


def build_mcp_surface(
    *,
    runtime_repository: RuntimeRepository,
    audit_repository: SqliteAuditRepository,
    skills: SkillCatalog,
    digest_key: bytes,
    public_base_url: str,
    client_factory: Callable[
        [TargetRecord, TargetCredentials], VcfTargetClient
    ]
    | None = None,
) -> McpSurface:
    """Build the private FastMCP instance and its mandatory dispatcher."""

    pool = ReadClientPool(
        runtime_repository, client_factory=client_factory
    )

    @asynccontextmanager
    async def lifespan(_server: FastMCP):
        try:
            yield
        finally:
            await pool.aclose()

    verifier = ApiKeyTokenVerifier(runtime_repository)
    base = public_base_url.rstrip("/")
    public_url = urlsplit(base)
    if not public_url.scheme or not public_url.hostname:
        raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL")
    public_host = public_url.netloc
    public_origin = f"{public_url.scheme}://{public_url.netloc}"
    mcp = FastMCP(
        "Sentania VCF Ops MCP (unofficial)",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=f"{base}/mcp",
            required_scopes=[],
        ),
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                public_host,
                f"{public_url.hostname}:*",
                "127.0.0.1:*",
                "localhost:*",
                "[::1]:*",
            ],
            allowed_origins=[
                public_origin,
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ],
        ),
    )

    registry = ToolRegistry()
    for adapter in READ_ADAPTERS:

        async def audited_handler(
            target: TargetRecord,
            arguments: Mapping[str, object],
            *,
            selected=adapter,
        ) -> Mapping[str, object]:
            client = await pool.get(target)
            return await selected.handler(client, **dict(arguments))

        registry.register(
            adapter.registration_mapping(audited_handler=audited_handler)
        )

    async def list_targets_handler(
        _target: TargetRecord,
        arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        allowed = {
            str(value) for value in arguments.get("allowed_targets", [])
        }
        targets = await runtime_repository.list()
        return {
            "targets": [
                {
                    "id": str(target.id),
                    "name": target.name,
                    "fqdn": target.fqdn,
                    "posture": target.posture.value,
                    "is_prod": target.is_prod,
                    "verify_ssl": target.verify_ssl,
                }
                for target in targets
                if str(target.id) in allowed
            ]
        }

    async def list_skills_handler(
        _target: TargetRecord,
        _arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        return {"skills": skills.list_skills()}

    async def get_skill_handler(
        _target: TargetRecord,
        arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        slug = str(arguments.get("slug", ""))
        version_value = arguments.get("version")
        version = None if version_value is None else str(version_value)
        skill = skills.get_skill(slug, version)
        if skill is None:
            raise KeyError("skill not found")
        return {
            "slug": skill.metadata.slug,
            "version": skill.metadata.version,
            "content": skill.content,
            "content_sha256": skill.metadata.content_sha256,
        }

    _register_local_tool(
        registry,
        name=LOCAL_TARGETS_TOOL,
        capability=Capability.READ_TARGETS,
        projection="targets-v1",
        path="/local/targets",
        handler=list_targets_handler,
    )
    _register_local_tool(
        registry,
        name=LOCAL_SKILLS_TOOL,
        capability=Capability.READ_SKILLS,
        projection="skills-index-v1",
        path="/local/skills",
        handler=list_skills_handler,
    )
    _register_local_tool(
        registry,
        name=LOCAL_SKILL_TOOL,
        capability=Capability.READ_SKILLS,
        projection="skill-content-v1",
        path="/local/skills/{slug}/{version}",
        handler=get_skill_handler,
    )
    registry.freeze()

    global_scopes = frozenset(
        spec.capability for spec in registry
    )
    reservations = FreeSpaceReservations(
        lambda: shutil.disk_usage(audit_repository.path.parent).free
    )
    dispatcher = Dispatcher(
        registry,
        DispatchDependencies(
            targets=runtime_repository,
            audit=audit_repository,
            global_scopes=global_scopes,
            digest_key=digest_key,
            reservations=reservations,
        ),
    )

    def make_read_tool(selected_name: str):
        async def invoke_read_tool(
            target_id: str,
            ctx: Context,
            arguments: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            identity = _identity_for_context(ctx)
            return await _dispatch(
                dispatcher,
                selected_name,
                ctx=ctx,
                identity=identity,
                target_id=TargetId(target_id),
                arguments=arguments or {},
            )

        return invoke_read_tool

    for adapter in READ_ADAPTERS:
        invoke_read_tool = make_read_tool(adapter.tool_name)
        invoke_read_tool.__name__ = adapter.tool_name
        mcp.tool(
            name=adapter.tool_name,
            description=(
                f"{adapter.summary} Pass adapter-specific parameters in "
                "the arguments object."
            ),
        )(invoke_read_tool)

    @mcp.tool(
        name=LOCAL_TARGETS_TOOL,
        description="List targets this API key is allowed to use.",
    )
    async def list_targets(ctx: Context) -> dict[str, Any]:
        identity = _identity_for_context(ctx)
        return await _dispatch(
            dispatcher,
            LOCAL_TARGETS_TOOL,
            ctx=ctx,
            identity=identity,
            target_id=_audit_anchor(identity),
            arguments={
                "allowed_targets": sorted(
                    str(target_id) for target_id in identity.allowed_targets
                )
            },
        )

    @mcp.tool(
        name=LOCAL_SKILLS_TOOL,
        description="List the operational skills bundled with this server.",
    )
    async def list_skills(ctx: Context) -> dict[str, Any]:
        identity = _identity_for_context(ctx)
        return await _dispatch(
            dispatcher,
            LOCAL_SKILLS_TOOL,
            ctx=ctx,
            identity=identity,
            target_id=_audit_anchor(identity),
            arguments={},
        )

    @mcp.tool(
        name=LOCAL_SKILL_TOOL,
        description="Read one bundled operational skill.",
    )
    async def get_skill(
        slug: str,
        ctx: Context,
        version: str | None = None,
    ) -> dict[str, Any]:
        identity = _identity_for_context(ctx)
        return await _dispatch(
            dispatcher,
            LOCAL_SKILL_TOOL,
            ctx=ctx,
            identity=identity,
            target_id=_audit_anchor(identity),
            arguments={"slug": slug, "version": version},
        )

    def make_skill_reader(content: str):
        async def read_skill_resource() -> str:
            _require_scope(Capability.READ_SKILLS)
            return content

        return read_skill_resource

    for skill in skills.skills:
        read_skill_resource = make_skill_reader(skill.content)

        mcp.resource(
            f"skill://{skill.metadata.slug}/{skill.metadata.version}",
            name=f"{skill.metadata.slug}@{skill.metadata.version}",
            description=skill.metadata.summary,
            mime_type="text/markdown",
        )(read_skill_resource)

    for slug in skills.current:
        skill = skills.get_skill(slug)
        if skill is None:
            continue

        read_current_skill = make_skill_reader(skill.content)
        use_current_skill = make_skill_reader(skill.content)

        mcp.resource(
            f"skill://{slug}/current",
            name=f"{slug}@current",
            description=skill.metadata.summary,
            mime_type="text/markdown",
        )(read_current_skill)
        mcp.prompt(
            name=f"use_{slug}",
            description=skill.metadata.summary,
        )(use_current_skill)

    mcp_app = mcp.streamable_http_app()
    return McpSurface(
        app=mcp_app,
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


def _register_local_tool(
    registry: ToolRegistry,
    *,
    name: str,
    capability: Capability,
    projection: str,
    path: str,
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
                method=HttpMethod.GET,
                path_template=path,
                permitted_query_parameters=frozenset(),
            ),
            "audited_handler": handler,
            "local.summary": "server-local read",
        }
    )


def _identity_for_context(ctx: Context) -> RequestIdentity:
    token = get_access_token()
    if token is None or token.client_id is None:
        raise PermissionError("authenticated API key identity is unavailable")
    claims = token.claims or {}
    targets = claims.get("allowed_targets", [])
    identity = RequestIdentity(
        key_id=token.client_id,
        granted_scopes=frozenset(token.scopes),
        allowed_targets=frozenset(TargetId(str(value)) for value in targets),
    )
    request = ctx.request_context.request
    if request is None:
        raise PermissionError("HTTP request context is unavailable")
    request.state.identity = identity
    return identity


def _require_scope(capability: CapabilityName) -> None:
    """Deny non-tool MCP readers that lack their advertised capability."""

    token = get_access_token()
    required = str(capability)
    if token is None or required not in token.scopes:
        raise PermissionError(f"API key requires scope {required}")


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
    identity: RequestIdentity,
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
