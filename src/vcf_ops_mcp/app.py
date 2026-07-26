import os
import typing
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware

from vcf_ops_mcp.contracts import AuditRepository

async def healthz(request: Request) -> JSONResponse:
    audit_repo: typing.Optional[AuditRepository] = getattr(request.app.state, "audit_repository", None)
    
    if audit_repo is not None:
        is_writable = await audit_repo.is_writable()
        unreconciled_count = await audit_repo.unreconciled_attempt_count()
        readiness = is_writable
        
        return JSONResponse(
            {
                "ready": readiness,
                "audit_writable": is_writable,
                "unreconciled_outcome_unknown_count": unreconciled_count,
            },
            status_code=200 if readiness else 503,
        )
    else:
        return JSONResponse(
            {
                "ready": False,
                "error": "Audit repository is unavailable",
            },
            status_code=503,
        )

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
