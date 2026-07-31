"""Server-rendered administration routes for the Phase 1 MVP."""

from __future__ import annotations

import functools
import os
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from vcf_ops_mcp.admin import auth
from vcf_ops_mcp.contracts import KeyId, TargetId
from vcf_ops_mcp.runtime_repository import (
    RuntimeRepository,
    RuntimeStoreUnavailable,
)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


class RepositoryUnavailable(RuntimeError):
    """The runtime configuration store is degraded or absent."""


def _repository(request: Request) -> RuntimeRepository:
    repository = getattr(request.app.state, "runtime_repository", None)
    if not isinstance(repository, RuntimeRepository):
        raise RepositoryUnavailable(
            "runtime configuration repository is unavailable"
        )
    return repository


def _degraded_to_503(endpoint):
    @functools.wraps(endpoint)
    async def wrapper(request: Request):
        try:
            return await endpoint(request)
        except (RepositoryUnavailable, RuntimeStoreUnavailable):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "message": (
                        "The configuration store is unavailable."
                        " Try again once the service reports healthy."
                    )
                },
                status_code=503,
            )

    return wrapper


async def require_auth(
    request: Request,
) -> RedirectResponse | None:
    timeout = auth.enforce_idle_timeout(request)
    if timeout:
        return timeout
    if "user_id" not in request.session:
        return RedirectResponse(url="/admin/login", status_code=303)
    return None


async def get_login(request: Request):
    if "user_id" in request.session:
        return RedirectResponse(url="/admin", status_code=303)
    repository = _repository(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "bootstrap_required": not await repository.has_admin(),
            "bootstrap_path": str(repository.bootstrap_password_path),
            "error": None,
        },
    )


async def post_login(request: Request):
    repository = _repository(request)
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    await repository.initialize_admin_from_bootstrap_file()
    valid = (
        secrets.compare_digest(username.encode("utf-8"), b"admin")
        and await repository.verify_admin_password(password)
    )
    if not valid:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "bootstrap_required": not await repository.has_admin(),
                "bootstrap_path": str(repository.bootstrap_password_path),
                "error": "Invalid credentials or bootstrap is not complete.",
            },
            status_code=401,
        )
    auth.initialize_session(request, "admin")
    return RedirectResponse(url="/admin", status_code=303)


async def get_dashboard(request: Request):
    check = await require_auth(request)
    if check:
        return check
    return await _dashboard_response(request)


async def get_auth_sources(request: Request):
    check = await require_auth(request)
    if check:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    # LOCAL is the only source whose wire value is proven for the MVP.
    # Arbitrary unauthenticated URL fetches from this route would be an SSRF
    # primitive, so additional discovery waits for a target-aware verifier.
    return JSONResponse(
        {"sources": [{"label": "Local users", "value": "LOCAL"}]}
    )


async def post_target_register(request: Request):
    check = await require_auth(request)
    if check:
        return check
    reauth = auth.require_recent_reauth(request)
    if reauth:
        return reauth
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "CSRF verification failed."},
            status_code=403,
        )
    try:
        await _repository(request).create_target(
            name=str(form.get("name", "")),
            fqdn=str(form.get("fqdn", "")),
            username=str(form.get("username", "")),
            password=str(form.get("password", "")),
            auth_source=str(form.get("auth_source", "LOCAL")),
            verify_ssl=form.get("verify_ssl") == "on",
        )
    except ValueError as exc:
        return await _dashboard_response(
            request, error=str(exc), status_code=400
        )
    auth.rotate_session(request)
    return RedirectResponse(url="/admin", status_code=303)


async def post_key_create(request: Request):
    check = await require_auth(request)
    if check:
        return check
    reauth = auth.require_recent_reauth(request)
    if reauth:
        return reauth
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "CSRF verification failed."},
            status_code=403,
        )
    repository = _repository(request)
    try:
        presented_key = await repository.create_api_key(
            label=str(form.get("label", "")),
            scopes=frozenset(
                str(value) for value in form.getlist("scope")
            ),
            allowed_targets=frozenset(
                TargetId(value) for value in form.getlist("target_id")
            ),
        )
    except ValueError as exc:
        return await _dashboard_response(
            request, error=str(exc), status_code=400
        )
    auth.rotate_session(request)
    return templates.TemplateResponse(
        request,
        "key_created.html",
        {"presented_key": presented_key},
        headers={"Cache-Control": "no-store"},
    )


async def post_key_revoke(request: Request):
    check = await require_auth(request)
    if check:
        return check
    reauth = auth.require_recent_reauth(request)
    if reauth:
        return reauth
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "CSRF verification failed."},
            status_code=403,
        )
    await _repository(request).revoke_api_key(
        KeyId(str(form.get("key_id", "")))
    )
    auth.rotate_session(request)
    return RedirectResponse(url="/admin", status_code=303)


async def get_reauth(request: Request):
    check = await require_auth(request)
    if check:
        return check
    return templates.TemplateResponse(
        request,
        "reauth.html",
        {"csrf_token": request.session["csrf_token"], "error": None},
    )


async def post_reauth(request: Request):
    check = await require_auth(request)
    if check:
        return check
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "CSRF verification failed."},
            status_code=403,
        )
    password = str(form.get("password", ""))
    if not await _repository(request).verify_admin_password(password):
        return templates.TemplateResponse(
            request,
            "reauth.html",
            {
                "csrf_token": request.session["csrf_token"],
                "error": "Invalid password.",
            },
            status_code=401,
        )
    destination = request.session.pop("next", "/admin")
    auth.refresh_reauth(request)
    if not isinstance(destination, str) or not destination.startswith("/admin"):
        destination = "/admin"
    return RedirectResponse(url=destination, status_code=303)


async def post_logout(request: Request):
    check = await require_auth(request)
    if check:
        return check
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "CSRF verification failed."},
            status_code=403,
        )
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


async def get_audit(request: Request):
    check = await require_auth(request)
    if check:
        return check
    repository = getattr(request.app.state, "audit_repository", None)
    try:
        records = await repository.recent_records(limit=200)
    except Exception:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "Audit records are temporarily unavailable."},
            status_code=503,
        )
    return templates.TemplateResponse(
        request,
        "audit.html",
        {"records": records, "csrf_token": request.session["csrf_token"]},
    )


async def _dashboard_response(
    request: Request,
    *,
    error: str | None = None,
    status_code: int = 200,
):
    repository = _repository(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "targets": await repository.list(),
            "api_keys": await repository.list_api_keys(),
            "grantable_scopes": sorted(
                str(scope)
                for scope in await repository.grantable_scopes()
            ),
            "csrf_token": request.session["csrf_token"],
            "error": error,
        },
        status_code=status_code,
    )


admin_routes = [
    Route("/admin/login", endpoint=_degraded_to_503(get_login), methods=["GET"]),
    Route("/admin/login", endpoint=_degraded_to_503(post_login), methods=["POST"]),
    Route("/admin/logout", endpoint=_degraded_to_503(post_logout), methods=["POST"]),
    Route("/admin/reauth", endpoint=_degraded_to_503(get_reauth), methods=["GET"]),
    Route("/admin/reauth", endpoint=_degraded_to_503(post_reauth), methods=["POST"]),
    Route("/admin", endpoint=_degraded_to_503(get_dashboard), methods=["GET"]),
    Route("/admin/audit", endpoint=_degraded_to_503(get_audit), methods=["GET"]),
    Route(
        "/admin/auth-sources",
        endpoint=_degraded_to_503(get_auth_sources),
        methods=["GET"],
    ),
    Route(
        "/admin/targets",
        endpoint=_degraded_to_503(post_target_register),
        methods=["POST"],
    ),
    Route("/admin/keys", endpoint=_degraded_to_503(post_key_create), methods=["POST"]),
    Route(
        "/admin/keys/revoke",
        endpoint=_degraded_to_503(post_key_revoke),
        methods=["POST"],
    ),
]
