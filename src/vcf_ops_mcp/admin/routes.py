import os
import typing

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from vcf_ops_mcp.admin import auth

# In tests or production, we might override this or use an env variable
# We won't strictly validate the template dir contents if we use string templates in tests,
# but for a real app we'll point to `templates/`.
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


async def require_auth(request: Request) -> typing.Optional[RedirectResponse]:
    timeout = auth.enforce_idle_timeout(request)
    if timeout:
        return timeout
    if "user_id" not in request.session:
        return RedirectResponse(url="/admin/login", status_code=303)
    return None


async def assert_audit_writable(request: Request) -> bool:
    audit_repo = getattr(request.app.state, "audit_repository", None)
    if audit_repo:
        return await audit_repo.is_writable()
    return False


async def get_login(request: Request):
    return HTMLResponse("<html><body>Login form</body></html>")


async def post_login(request: Request):
    return HTMLResponse("Login is not yet implemented. Missing secure credential storage.", status_code=501)


async def get_dashboard(request: Request):
    check = await require_auth(request)
    if check:
        return check
    return HTMLResponse("<html><body>Dashboard</body></html>")


async def get_auth_sources(request: Request):
    check = await require_auth(request)
    if check:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    fqdn = request.query_params.get("fqdn")
    if not fqdn:
        return JSONResponse({"sources": [{"label": "Local users", "value": "LOCAL"}]})

    url = f"https://{fqdn}/suite-api/api/auth/sources"
    try:
        # Use verify=False per spec for unauthenticated recon (we don't have the CA yet)
        async with httpx.AsyncClient(verify=False, timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                sources = [{"label": "Local users", "value": "LOCAL"}] + [
                    {"label": s.get("name"), "value": s.get("name")} for s in data.get("sources", []) if s.get("name")
                ]
                return JSONResponse({"sources": sources})
    except Exception:
        pass

    return JSONResponse({"sources": [{"label": "Local users", "value": "LOCAL"}]})


async def post_target_register(request: Request):
    check = await require_auth(request)
    if check:
        return check

    reauth = auth.require_recent_reauth(request)
    if reauth:
        return reauth

    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return HTMLResponse("CSRF verification failed.", status_code=403)

    # Rotate session on sensitive write
    auth.rotate_session(request)

    return HTMLResponse("Target registration is not yet implemented. Missing target repository.", status_code=501)


admin_routes = [
    Route("/admin/login", endpoint=get_login, methods=["GET"]),
    Route("/admin/login", endpoint=post_login, methods=["POST"]),
    Route("/admin", endpoint=get_dashboard, methods=["GET"]),
    Route("/admin/auth-sources", endpoint=get_auth_sources, methods=["GET"]),
    Route("/admin/targets", endpoint=post_target_register, methods=["POST"]),
]
