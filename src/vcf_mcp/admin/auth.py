import hashlib
import os
import secrets
import time

from starlette.requests import Request
from starlette.responses import RedirectResponse

# Security constants
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
IDLE_TIMEOUT_SECONDS = 15 * 60  # 15 minutes
RECENT_REAUTH_WINDOW_SECONDS = 5 * 60  # 5 minutes
DISCARDED_POST_NOTICE_SECONDS = 5 * 60  # 5 minutes
DISCARDED_POST_NOTICE = (
    "Your submitted change was not saved because recent password confirmation "
    "was required. Confirm your password, then submit the change again."
)
_DISCARDED_POST_NOTICE_KEY = "discarded_post_notice"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    hashed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return f"{salt.hex()}:{hashed.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt_hex, hash_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        actual_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        return secrets.compare_digest(expected_hash, actual_hash)
    except ValueError:
        return False


def initialize_session(request: Request, user_id: str) -> None:
    request.session.clear()
    request.session["user_id"] = user_id
    now = time.time()
    request.session["last_active"] = now
    request.session["auth_time"] = now
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    request.session["session_id"] = secrets.token_urlsafe(32)


def enforce_idle_timeout(request: Request) -> RedirectResponse | None:
    if "user_id" not in request.session:
        return None

    last_active = request.session.get("last_active")
    now = time.time()
    
    if not last_active or (now - last_active > IDLE_TIMEOUT_SECONDS):
        request.session.clear()
        return RedirectResponse(url="/admin/login", status_code=303)
        
    request.session["last_active"] = now
    return None


def rotate_session(request: Request) -> None:
    """Rotates session identity to prevent fixation.
    
    Since Starlette SessionMiddleware uses cookie-based sessions,
    changing the CSRF token and internal IDs forces a new cookie value.
    """
    if "user_id" in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        request.session["session_id"] = secrets.token_urlsafe(32)


def is_recent_reauth(request: Request) -> bool:
    auth_time = request.session.get("auth_time")
    if not auth_time:
        return False
    return (time.time() - auth_time) < RECENT_REAUTH_WINDOW_SECONDS


def refresh_reauth(request: Request) -> None:
    """Extend the recent-reauth window without rotating session tokens."""
    now = time.time()
    request.session["auth_time"] = now
    request.session["last_active"] = now


def require_recent_reauth(
    request: Request, *, next_path: str = "/admin"
) -> RedirectResponse | None:
    if not is_recent_reauth(request):
        # Store only a local path, and only for safe methods. A full URL
        # would turn this into an open redirect if proxy headers or a future
        # caller supplied another host, and a POST-only path would land the
        # post-reauth GET redirect on a 405.
        path = next_path if next_path.startswith("/admin") else "/admin"
        if request.scope.get("method", "").upper() in {"GET", "HEAD"}:
            candidate = request.scope.get("path")
            if not isinstance(candidate, str):
                value = request.url
                candidate = getattr(value, "path", str(value))
            if candidate.startswith(("http://", "https://")):
                candidate = "/" + candidate.split("/", 3)[-1]
            if candidate.startswith("/"):
                path = candidate
        else:
            record_discarded_post_notice(request)
        request.session["next"] = path
        return RedirectResponse(url="/admin/reauth", status_code=303)
    return None


def record_discarded_post_notice(request: Request) -> None:
    request.session[_DISCARDED_POST_NOTICE_KEY] = {
        "message": DISCARDED_POST_NOTICE,
        "expires_at": time.time() + DISCARDED_POST_NOTICE_SECONDS,
    }


def discarded_post_notice(request: Request, *, consume: bool = False) -> str | None:
    """Return the short-lived notice for a POST discarded at the reauth gate."""
    value = request.session.get(_DISCARDED_POST_NOTICE_KEY)
    if not isinstance(value, dict):
        request.session.pop(_DISCARDED_POST_NOTICE_KEY, None)
        return None
    message = value.get("message")
    expires_at = value.get("expires_at")
    if (
        not isinstance(message, str)
        or not isinstance(expires_at, (int, float))
        or time.time() >= expires_at
    ):
        request.session.pop(_DISCARDED_POST_NOTICE_KEY, None)
        return None
    if consume:
        request.session.pop(_DISCARDED_POST_NOTICE_KEY, None)
    return message


def verify_csrf(request: Request, submitted_token: str) -> bool:
    expected = request.session.get("csrf_token")
    if not isinstance(expected, str) or not expected or not submitted_token:
        return False
    return secrets.compare_digest(
        expected.encode("utf-8"), submitted_token.encode("utf-8")
    )
