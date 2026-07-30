import os
import typing
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware

from vcf_ops_mcp.contracts import AuditRepository

async def healthz(request: Request) -> JSONResponse:
    """Report readiness, which is exactly audit write capability.

    200 if and only if the audit store accepts a durable write. Every other
    condition is 503. A server that cannot record what it did must not be
    routed traffic, per the constitution's audit invariant, so this endpoint
    never reports ready on an unproven store and never treats "the store could
    not be queried" as "the store is fine".
    """

    audit_repo: typing.Optional[AuditRepository] = getattr(request.app.state, "audit_repository", None)

    if audit_repo is None:
        return JSONResponse(
            {
                "ready": False,
                "audit_writable": False,
                "unreconciled_outcome_unknown_count": None,
                "error": "Audit repository is unavailable",
            },
            status_code=503,
        )

    try:
        is_writable = await audit_repo.is_writable()
    except Exception:
        is_writable = False

    # An unreadable count must never be reported as zero. Null says "unknown",
    # and readiness is already false whenever the store cannot be reached.
    try:
        unreconciled_count: typing.Optional[int] = await audit_repo.unreconciled_attempt_count()
    except Exception:
        unreconciled_count = None

    body: dict[str, object] = {
        "ready": is_writable,
        "audit_writable": is_writable,
        "unreconciled_outcome_unknown_count": unreconciled_count,
    }
    if not is_writable:
        body["error"] = "Audit repository is not writable"
    return JSONResponse(body, status_code=200 if is_writable else 503)

from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from mcp.server.fastmcp import FastMCP

from vcf_ops_mcp.admin.routes import admin_routes

class StructuralAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        SECURITY_WRITE_ROUTES = ["/admin/targets"]
        if request.url.path in SECURITY_WRITE_ROUTES and request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            audit_repo = getattr(request.app.state, "audit_repository", None)
            is_writable = False
            if audit_repo:
                is_writable = await audit_repo.is_writable()
            if not is_writable:
                return HTMLResponse("Audit is degraded; security-relevant writes are disabled.", status_code=503)
        return await call_next(request)

def create_app(audit_repository: typing.Optional[AuditRepository] = None) -> Starlette:
    mcp = FastMCP("Sentania VCF Ops MCP (unofficial)")
    
    secret_key = os.environ.get("SESSION_SECRET")
    if not secret_key:
        raise RuntimeError("SESSION_SECRET must be set for production session encryption")

    app = Starlette(
        routes=[
            Route("/healthz", endpoint=healthz, methods=["GET"]),
        ] + admin_routes,
        middleware=[
            Middleware(SessionMiddleware, secret_key=secret_key),
            Middleware(StructuralAuditMiddleware)
        ]
    )
    
    # Mount MCP streamable HTTP transport
    app.mount("/mcp", mcp.streamable_http_app())
    
    app.state.audit_repository = audit_repository
    return app
