"""Starlette parent application for health, admin, and MCP surfaces."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from vcf_mcp.admin.routes import admin_routes
from vcf_mcp.contracts import AuditRepository
from vcf_mcp.mcp_server import McpSurface, McpSurfaces
from vcf_mcp.runtime_repository import RuntimeRepository
from vcf_mcp.pack_trust import PackTrustManager


async def healthz(request: Request) -> JSONResponse:
    """Report ready only when every production persistence dependency works."""

    audit_repo: AuditRepository | None = getattr(
        request.app.state, "audit_repository", None
    )
    if audit_repo is None:
        audit_writable = False
        unreconciled_count: int | None = None
    else:
        try:
            audit_writable = await audit_repo.is_writable()
        except Exception:
            audit_writable = False
        try:
            unreconciled_count = await audit_repo.unreconciled_attempt_count()
        except Exception:
            unreconciled_count = None

    runtime_repo: RuntimeRepository | None = getattr(
        request.app.state, "runtime_repository", None
    )
    if runtime_repo is None:
        configuration_ready = getattr(request.app.state, "configuration_ready", True)
    else:
        try:
            configuration_ready = await runtime_repo.is_ready()
        except Exception:
            configuration_ready = False
    session_secret_persistent = bool(
        getattr(request.app.state, "session_secret_persistent", True)
    )
    mcp_ready = bool(getattr(request.app.state, "mcp_ready", True))
    ready = (
        audit_writable
        and configuration_ready
        and session_secret_persistent
        and mcp_ready
    )
    body: dict[str, object] = {
        "ready": ready,
        "audit_writable": audit_writable,
        "configuration_ready": configuration_ready,
        "session_secret_persistent": session_secret_persistent,
        "mcp_ready": mcp_ready,
        "unreconciled_outcome_unknown_count": unreconciled_count,
    }
    if not ready:
        failed = [
            name
            for name, healthy in (
                ("audit", audit_writable),
                ("configuration", configuration_ready),
                ("session_secret", session_secret_persistent),
                ("mcp", mcp_ready),
            )
            if not healthy
        ]
        body["error"] = f"Unavailable dependencies: {', '.join(failed)}"
    return JSONResponse(body, status_code=200 if ready else 503)


async def unavailable_mcp(_request: Request) -> JSONResponse:
    return JSONResponse({"error": "MCP runtime is unavailable"}, status_code=503)


class StructuralAuditMiddleware(BaseHTTPMiddleware):
    """Refuse security-relevant admin writes while audit storage is degraded."""

    _SECURITY_WRITE_PREFIXES = (
        "/admin/targets",
        "/admin/keys",
        "/admin/authorization-mode",
        "/admin/credential-rotation",
        "/admin/packs",
    )

    async def dispatch(self, request: Request, call_next):
        is_security_write = request.method in {
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
        } and request.url.path.startswith(self._SECURITY_WRITE_PREFIXES)
        if is_security_write:
            audit_repo = getattr(request.app.state, "audit_repository", None)
            try:
                is_writable = bool(audit_repo and await audit_repo.is_writable())
            except Exception:
                is_writable = False
            if not is_writable:
                return HTMLResponse(
                    "Audit is degraded; security-relevant writes are disabled.",
                    status_code=503,
                )
        return await call_next(request)


def create_app(
    audit_repository: AuditRepository | None = None,
    *,
    session_secret: str | None = None,
    session_secret_persistent: bool = True,
    runtime_repository: RuntimeRepository | None = None,
    mcp_surface: McpSurface | None = None,
    mcp_surfaces: McpSurfaces | None = None,
    configuration_ready: bool = True,
    mcp_ready: bool | None = None,
    session_https_only: bool = True,
    pack_trust_manager: PackTrustManager | None = None,
) -> Starlette:
    """Compose the parent app while retaining explicit test seams."""

    secret_key = session_secret or os.environ.get("SESSION_SECRET")
    if not secret_key:
        raise RuntimeError(
            "a session secret must be injected by the production composition root"
        )

    routes: list[Route | Mount] = [
        Route("/healthz", endpoint=healthz, methods=["GET"]),
        *admin_routes,
    ]
    lifespan = None
    if mcp_surfaces is not None:
        for endpoint, surface in mcp_surfaces.by_endpoint.items():
            routes.append(Mount(f"/{endpoint}/mcp", app=surface.app))

        @asynccontextmanager
        async def combined_lifespan(_app: Starlette):
            async with AsyncExitStack() as stack:
                for surface in mcp_surfaces.by_endpoint.values():
                    await stack.enter_async_context(
                        surface.app.router.lifespan_context(surface.app)
                    )
                yield

        lifespan = combined_lifespan
    elif mcp_surface is None:
        routes.extend(
            [
                Route(
                    "/mcp",
                    endpoint=unavailable_mcp,
                    methods=["GET", "POST", "DELETE"],
                ),
                Route(
                    "/mcp/{path:path}",
                    endpoint=unavailable_mcp,
                    methods=["GET", "POST", "DELETE"],
                ),
            ]
        )
    else:
        routes.append(Mount("/mcp", app=mcp_surface.app))
        lifespan = mcp_surface.app.router.lifespan_context

    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(
                SessionMiddleware,
                secret_key=secret_key,
                session_cookie="vcf_mcp_admin",
                max_age=15 * 60,
                same_site="strict",
                https_only=session_https_only,
            ),
            Middleware(StructuralAuditMiddleware),
        ],
    )
    app.state.audit_repository = audit_repository
    app.state.runtime_repository = runtime_repository
    app.state.configuration_ready = configuration_ready
    app.state.session_secret_persistent = session_secret_persistent
    app.state.mcp_ready = (
        mcp_surface is not None
        or mcp_surfaces is not None
        or runtime_repository is None
        if mcp_ready is None
        else mcp_ready
    )
    app.state.target_invalidator = (
        None if mcp_surfaces is None else mcp_surfaces.invalidator
    )
    app.state.mcp_surfaces = mcp_surfaces
    app.state.pack_trust_manager = pack_trust_manager
    return app
