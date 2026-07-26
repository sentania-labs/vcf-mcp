import hashlib
import os
import secrets
import time
import typing

from starlette.requests import Request
from starlette.responses import RedirectResponse

# Security constants
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
IDLE_TIMEOUT_SECONDS = 15 * 60  # 15 minutes
RECENT_REAUTH_WINDOW_SECONDS = 5 * 60  # 5 minutes


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


def enforce_idle_timeout(request: Request) -> typing.Optional[RedirectResponse]:
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


def require_recent_reauth(request: Request) -> typing.Optional[RedirectResponse]:
    if not is_recent_reauth(request):
        # Stash current path to redirect back after re-auth
        request.session["next"] = str(request.url)
        return RedirectResponse(url="/admin/reauth", status_code=303)
    return None


def verify_csrf(request: Request, submitted_token: str) -> bool:
    expected = request.session.get("csrf_token")
    if not expected or not submitted_token:
        return False
    return secrets.compare_digest(expected, submitted_token)
