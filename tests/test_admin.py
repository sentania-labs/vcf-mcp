from unittest import mock

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from vcf_mcp.admin import auth
from vcf_mcp.admin.routes import admin_routes
from vcf_mcp.app import StructuralAuditMiddleware


def create_admin_app(audit_writable: bool = True):
    class MockAuditRepo:
        async def is_writable(self):
            return audit_writable

    async def test_setup_session(request):
        auth.initialize_session(request, "admin")
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=admin_routes + [Route("/admin/test-setup-session", endpoint=test_setup_session, methods=["GET"])],
        middleware=[
            Middleware(SessionMiddleware, secret_key="test-secret"),
            Middleware(StructuralAuditMiddleware)
        ],
    )
    app.state.audit_repository = MockAuditRepo()
    return app

@pytest.fixture
def logged_in_client():
    app = create_admin_app()
    client = TestClient(app)
    # Login to set up the session
    resp = client.get("/admin/test-setup-session")
    assert resp.status_code == 200
    return client

def test_auth_sources_api_no_fqdn(logged_in_client):
    resp = logged_in_client.get("/admin/auth-sources")
    assert resp.status_code == 200
    assert resp.json() == {"sources": [{"label": "Local users", "value": "LOCAL"}]}

def test_auth_sources_does_not_fetch_an_arbitrary_fqdn():
    app = create_admin_app()
    client = TestClient(app)
    client.get("/admin/test-setup-session")
    with mock.patch("httpx.AsyncClient.get") as outbound:
        resp = client.get("/admin/auth-sources?fqdn=test.local")
    assert resp.status_code == 200
    assert resp.json() == {
        "sources": [{"label": "Local users", "value": "LOCAL"}]
    }
    outbound.assert_not_called()

def test_security_write_fails_closed_when_audit_degraded():
    app = create_admin_app(audit_writable=False)
    client = TestClient(app)
    
    # We need to manually set a valid session for the client to bypass auth
    # because login won't set a valid CSRF token if we mock the session.
    # We'll just login first.
    client.get("/admin/test-setup-session")
    
    # Now try to write
    resp = client.post("/admin/targets", data={"csrf_token": "dummy"}, follow_redirects=False)
    # Because audit is degraded, it should fail 503 before even checking CSRF
    assert resp.status_code == 503
    assert b"Audit is degraded" in resp.content

def test_security_write_fails_invalid_csrf(logged_in_client):
    # audit is writable in this client
    resp = logged_in_client.post("/admin/targets", data={"csrf_token": "wrong"}, follow_redirects=False)
    assert resp.status_code == 403
    assert b"CSRF" in resp.content

def test_security_write_fails_non_ascii_csrf(logged_in_client):
    resp = logged_in_client.post(
        "/admin/targets",
        data={"csrf_token": "tökén"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    assert b"CSRF" in resp.content

def test_degraded_repository_answers_503_not_500():
    app = create_admin_app()
    client = TestClient(app)
    resp = client.get("/admin/login")
    assert resp.status_code == 503
    assert b"unavailable" in resp.content

def test_degraded_repository_answers_503_when_logged_in():
    app = create_admin_app()
    client = TestClient(app)
    client.get("/admin/test-setup-session")
    resp = client.get("/admin")
    assert resp.status_code == 503
    assert b"unavailable" in resp.content

def test_security_write_requires_recent_reauth():
    app = create_admin_app()
    client = TestClient(app)
    
    # Login but force the auth_time to be stale
    with mock.patch("time.time") as mock_time:
        mock_time.return_value = 10000.0
        client.get("/admin/test-setup-session")
        
        # Advance time past the recent reauth window
        mock_time.return_value = 10000.0 + auth.RECENT_REAUTH_WINDOW_SECONDS + 10
        
        resp = client.post("/admin/targets", data={"csrf_token": "dummy"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "/admin/reauth" in resp.headers["location"]
