import time

from starlette.requests import Request
from starlette.responses import RedirectResponse

from vcf_ops_mcp.admin import auth


def test_password_hashing():
    password = "correcthorsebatterystaple"
    hashed = auth.hash_password(password)
    
    assert auth.verify_password(password, hashed)
    assert not auth.verify_password("wrong", hashed)
    
    # Check shape: salt:hash
    parts = hashed.split(":")
    assert len(parts) == 2
    # Ensure it's not a plain comparison
    assert password not in hashed

def build_mock_request(session_data: dict, method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "session": session_data,
        "url": "http://testserver/path",
    }
    class MockRequest(Request):
        @property
        def url(self):
            return "http://testserver/path"
    return MockRequest(scope)

def test_initialize_session():
    req = build_mock_request({})
    auth.initialize_session(req, "admin")
    
    assert req.session["user_id"] == "admin"
    assert "last_active" in req.session
    assert "auth_time" in req.session
    assert "csrf_token" in req.session
    assert len(req.session["csrf_token"]) > 20

def test_enforce_idle_timeout():
    # Not logged in
    req = build_mock_request({})
    assert auth.enforce_idle_timeout(req) is None
    
    # Active
    now = time.time()
    req = build_mock_request({
        "user_id": "admin",
        "last_active": now - 100,  # 100 seconds ago
    })
    result = auth.enforce_idle_timeout(req)
    assert result is None
    assert req.session["last_active"] >= now
    
    # Idle
    req = build_mock_request({
        "user_id": "admin",
        "last_active": now - auth.IDLE_TIMEOUT_SECONDS - 10,
    })
    result = auth.enforce_idle_timeout(req)
    assert isinstance(result, RedirectResponse)
    assert result.status_code == 303
    assert result.headers["location"] == "/admin/login"
    assert "user_id" not in req.session  # Cleared

def test_rotate_session():
    req = build_mock_request({
        "user_id": "admin",
        "csrf_token": "old-token",
    })
    auth.rotate_session(req)
    assert req.session["csrf_token"] != "old-token"
    assert len(req.session["csrf_token"]) > 20

def test_recent_reauth():
    now = time.time()
    
    # Recent
    req = build_mock_request({
        "user_id": "admin",
        "auth_time": now - 100,
    })
    assert auth.is_recent_reauth(req) is True
    assert auth.require_recent_reauth(req) is None
    
    # Stale
    req = build_mock_request({
        "user_id": "admin",
        "auth_time": now - auth.RECENT_REAUTH_WINDOW_SECONDS - 10,
    })
    assert auth.is_recent_reauth(req) is False
    result = auth.require_recent_reauth(req)
    assert isinstance(result, RedirectResponse)
    assert result.status_code == 303
    assert result.headers["location"] == "/admin/reauth"
    assert req.session["next"] == "/path"

def test_stale_reauth_from_a_post_returns_to_the_dashboard():
    now = time.time()
    req = build_mock_request(
        {
            "user_id": "admin",
            "auth_time": now - auth.RECENT_REAUTH_WINDOW_SECONDS - 10,
        },
        method="POST",
    )
    result = auth.require_recent_reauth(req)
    assert isinstance(result, RedirectResponse)
    assert result.headers["location"] == "/admin/reauth"
    assert req.session["next"] == "/admin"

def test_refresh_reauth_preserves_the_csrf_token():
    now = time.time()
    req = build_mock_request({
        "user_id": "admin",
        "auth_time": now - auth.RECENT_REAUTH_WINDOW_SECONDS - 10,
        "csrf_token": "existing-token",
        "session_id": "existing-session",
    })
    auth.refresh_reauth(req)
    assert auth.is_recent_reauth(req) is True
    assert req.session["csrf_token"] == "existing-token"
    assert req.session["session_id"] == "existing-session"

def test_csrf_verification():
    req = build_mock_request({
        "csrf_token": "expected-token",
    })
    assert auth.verify_csrf(req, "expected-token") is True
    assert auth.verify_csrf(req, "wrong-token") is False
    assert auth.verify_csrf(req, "") is False
    assert auth.verify_csrf(req, "wröng-töken") is False
    
    req_no_token = build_mock_request({})
    assert auth.verify_csrf(req_no_token, "expected-token") is False
