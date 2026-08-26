"""Persistent runtime secret helpers.

The production container has a writable ``/keys`` volume and a read-only root
filesystem. Secrets created here are written atomically on that volume with
mode 0600, then reused on every later process start.
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path

DEFAULT_SESSION_SECRET_PATH = Path("/keys/session_secret")
DEFAULT_AUDIT_DIGEST_KEY_PATH = Path("/keys/audit_digest_key")
MINIMUM_SESSION_SECRET_BYTES = 32
PRIVATE_FILE_MODE = 0o600
GROUP_OR_OTHER_ACCESS = 0o077
OTHER_ACCESS = 0o007
LOGGER = logging.getLogger(__name__)


class SecretStoreUnavailable(RuntimeError):
    """Raised when persistent secret material cannot be loaded safely."""


def session_secret_path_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("SESSION_SECRET_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_SESSION_SECRET_PATH


def load_or_create_session_secret(
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Return the explicit override or a durable generated signing secret."""

    values = os.environ if environment is None else environment
    override = values.get("SESSION_SECRET", "")
    if override:
        _validate_secret(override)
        return override

    path = session_secret_path_from_environment(values)
    if path.exists():
        value = _read_private_text(path)
        _validate_secret(value)
        return value

    generated = secrets.token_urlsafe(48)
    _validate_secret(generated)
    _atomic_private_write(path, generated)
    value = _read_private_text(path)
    _validate_secret(value)
    return value


def audit_digest_key_path_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("AUDIT_DIGEST_KEY_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_AUDIT_DIGEST_KEY_PATH


def load_or_create_audit_digest_key(
    *,
    environment: Mapping[str, str] | None = None,
) -> bytes:
    """Return the durable HMAC key for audit argument digests."""

    return load_or_create_private_bytes(
        audit_digest_key_path_from_environment(environment)
    )


def load_or_create_private_bytes(path: Path, *, size: int = 32) -> bytes:
    """Load or atomically create a fixed-size private binary key."""

    if path.exists():
        value = _read_private_bytes(path)
        if len(value) != size:
            raise SecretStoreUnavailable(
                f"{path} must contain exactly {size} bytes"
            )
        return value

    generated = secrets.token_bytes(size)
    _atomic_private_write(path, generated)
    value = _read_private_bytes(path)
    if len(value) != size:
        raise SecretStoreUnavailable(
            f"{path} must contain exactly {size} bytes"
        )
    return value


def atomic_private_text_write(path: Path, value: str) -> None:
    """Write a private text file atomically, replacing an existing value."""

    _atomic_private_write(path, value)


def read_private_text(path: Path) -> str:
    return _read_private_text(path)


def validate_private_file(path: Path) -> os.stat_result:
    """Require an owned regular file with no access outside its service group."""

    try:
        details = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise SecretStoreUnavailable(f"cannot stat private file {path}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise SecretStoreUnavailable(f"private path is not a regular file: {path}")
    if details.st_uid != os.geteuid():
        raise SecretStoreUnavailable(
            f"private file {path} is owned by uid {details.st_uid}, but the service"
            f" runs as uid {os.geteuid()}; set ownership to uid {os.geteuid()}"
        )

    mode = stat.S_IMODE(details.st_mode)
    if mode & GROUP_OR_OTHER_ACCESS:
        try:
            os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)
        except OSError as exc:
            if mode & OTHER_ACCESS:
                raise SecretStoreUnavailable(
                    f"private file {path} has mode {mode:04o}, which grants access"
                    " to users outside the service group, and automatic correction"
                    f" to 0600 failed ({exc}); set mode to 0600 or remove all"
                    " 'other' permissions"
                ) from exc
            LOGGER.warning(
                "private file %s has mode %04o and could not be tightened to 0600"
                " (%s); continuing because only service-owner and group access is"
                " present",
                path,
                mode,
                exc,
            )
        else:
            LOGGER.warning(
                "private file %s had mode %04o and was corrected to 0600",
                path,
                mode,
            )
            try:
                details = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise SecretStoreUnavailable(
                    f"cannot verify corrected private file {path}; check the"
                    " mounted volume and file permissions"
                ) from exc
    return details


def _validate_secret(value: str) -> None:
    if "\n" in value or "\r" in value:
        raise SecretStoreUnavailable("SESSION_SECRET must be one line")
    if len(value.encode("utf-8")) < MINIMUM_SESSION_SECRET_BYTES:
        raise SecretStoreUnavailable(
            "SESSION_SECRET must contain at least 32 bytes"
        )


def _read_private_text(path: Path) -> str:
    raw = _read_private_bytes(path)
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretStoreUnavailable(f"private file is not UTF-8: {path}") from exc
    return value


def _read_private_bytes(path: Path) -> bytes:
    details = validate_private_file(path)
    if details.st_size > 16 * 1024:
        raise SecretStoreUnavailable(f"private file is unexpectedly large: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SecretStoreUnavailable(f"cannot read private file {path}") from exc


def _atomic_private_write(path: Path, value: str | bytes) -> None:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary.fileno(), 0o600)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        raise SecretStoreUnavailable(
            f"cannot persist private file {path}"
        ) from exc
