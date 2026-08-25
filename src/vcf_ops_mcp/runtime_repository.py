"""Volume-backed runtime configuration for the Phase 1 MVP.

Targets, the bootstrap-admin password hash, and API-key digests live in one
SQLite database on ``/data``. VCF Ops credentials are encrypted with AES-GCM
using a versioned keyring on the separate ``/keys`` volume. Plaintext target
credentials and presented API keys are never stored.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import re
import secrets
import sqlite3
import ssl
import threading
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vcf_ops_mcp.admin.auth import hash_password, verify_password
from vcf_ops_mcp.contracts import (
    BackendKind,
    CapabilityName,
    ConfigurationGeneration,
    KeyId,
    RequestIdentity,
    TargetConfigurationChange,
    TargetId,
    TargetPosture,
    TargetRecord,
)
from vcf_ops_mcp.security import (
    SecretStoreUnavailable,
    atomic_private_text_write,
    read_private_text,
)
from vcf_ops_mcp.vcf.client import TargetCredentials

DEFAULT_CONFIG_DB_PATH = Path("/data/config.sqlite3")
DEFAULT_CREDENTIAL_KEYRING_PATH = Path("/keys/credential_keyring.json")
DEFAULT_ADMIN_BOOTSTRAP_PASSWORD_FILE = Path("/keys/admin_bootstrap_password")
PRODUCTION_FQDN = "vcf-lab-operations.int.sentania.net"
SCHEMA_VERSION = 2
ENVELOPE_SCHEMA_VERSION = 1
KEYRING_VERSION = 1
MINIMUM_ADMIN_PASSWORD_BYTES = 16
_FQDN = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


class RuntimeStoreUnavailable(RuntimeError):
    """Raised when runtime configuration cannot be used safely."""


def config_db_path_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("CONFIG_DB_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_CONFIG_DB_PATH


def credential_keyring_path_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("CREDENTIAL_KEYRING_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_CREDENTIAL_KEYRING_PATH


def admin_bootstrap_path_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("ADMIN_BOOTSTRAP_PASSWORD_FILE", "").strip()
    return Path(configured) if configured else DEFAULT_ADMIN_BOOTSTRAP_PASSWORD_FILE


class RuntimeRepository:
    """Concrete target, credential, API-key, and admin repository."""

    def __init__(
        self,
        database_path: Path,
        keyring_path: Path,
        *,
        grantable_scopes: frozenset[CapabilityName],
        bootstrap_password_path: Path | None = None,
    ) -> None:
        self.database_path = database_path
        self.keyring_path = keyring_path
        self.bootstrap_password_path = (
            bootstrap_password_path or DEFAULT_ADMIN_BOOTSTRAP_PASSWORD_FILE
        )
        self._grantable_scopes = grantable_scopes
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._active_key_id: str | None = None
        self._keys: dict[str, bytes] = {}

    def bootstrap(self) -> None:
        """Open storage, create its schema, and load the credential keyring."""

        with self._lock:
            try:
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(
                    self.database_path,
                    timeout=5.0,
                    check_same_thread=False,
                )
                os.chmod(self.database_path, 0o600)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=5000")
                self._create_schema(connection)
                self._connection = connection
                has_credentials = bool(
                    connection.execute("SELECT 1 FROM targets LIMIT 1").fetchone()
                )
                self._load_or_create_keyring(refuse_generation=has_credentials)
            except (OSError, sqlite3.Error, SecretStoreUnavailable, ValueError) as exc:
                self.close()
                raise RuntimeStoreUnavailable(
                    f"runtime store at {self.database_path} is unavailable"
                ) from exc

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._active_key_id = None
            self._keys.clear()

    async def is_ready(self) -> bool:
        try:
            return await asyncio.to_thread(self._is_ready_sync)
        except (OSError, sqlite3.Error, RuntimeStoreUnavailable):
            return False

    async def has_admin(self) -> bool:
        return await asyncio.to_thread(self._has_admin_sync)

    async def initialize_admin_from_bootstrap_file(self) -> bool:
        """Consume the approved bootstrap password file exactly once."""

        return await asyncio.to_thread(self._initialize_admin_from_bootstrap_file_sync)

    async def set_admin_password_for_test(self, password: str) -> None:
        """Initialize the admin hash without a filesystem ceremony in tests."""

        await asyncio.to_thread(self._set_admin_password_sync, password)

    async def verify_admin_password(self, password: str) -> bool:
        return await asyncio.to_thread(self._verify_admin_password_sync, password)

    async def get(self, target_id: TargetId) -> TargetRecord | None:
        return await asyncio.to_thread(self._get_sync, target_id)

    async def list(self) -> tuple[TargetRecord, ...]:
        return await asyncio.to_thread(self._list_sync)

    def list_at_startup(self) -> tuple[TargetRecord, ...]:
        """Read startup wiring before the ASGI event loop begins."""

        return self._list_sync()

    async def create_target(
        self,
        *,
        name: str,
        fqdn: str,
        username: str,
        password: str,
        auth_source: str,
        verify_ssl: bool,
        backend: BackendKind | str = BackendKind.OPS,
        root_ca_pem: str | None = None,
    ) -> TargetRecord:
        return await asyncio.to_thread(
            self._create_target_sync,
            name,
            fqdn,
            username,
            password,
            auth_source,
            verify_ssl,
            backend,
            root_ca_pem,
        )

    async def get_credentials(self, target_id: TargetId) -> TargetCredentials:
        return await asyncio.to_thread(self._get_credentials_sync, target_id)

    async def get_root_ca(self, target_id: TargetId) -> str | None:
        return await asyncio.to_thread(self._get_root_ca_sync, target_id)

    async def update_target(
        self,
        *,
        target_id: TargetId,
        expected_generation: ConfigurationGeneration,
        name: str,
        fqdn: str,
        username: str | None,
        password: str | None,
        auth_source: str,
        verify_ssl: bool,
        posture: TargetPosture,
        root_ca_pem: str | None = None,
        clear_root_ca: bool = False,
    ) -> tuple[TargetRecord, TargetConfigurationChange]:
        return await asyncio.to_thread(
            self._update_target_sync,
            target_id,
            expected_generation,
            name,
            fqdn,
            username,
            password,
            auth_source,
            verify_ssl,
            posture,
            root_ca_pem,
            clear_root_ca,
        )

    async def save(
        self,
        target: TargetRecord,
        *,
        expected_generation: ConfigurationGeneration | None,
    ) -> TargetConfigurationChange:
        return await asyncio.to_thread(self._save_sync, target, expected_generation)

    async def create_api_key(
        self,
        *,
        label: str,
        scopes: frozenset[CapabilityName],
        allowed_targets: frozenset[TargetId],
        allowed_endpoints: frozenset[str] | None = None,
    ) -> str:
        return await asyncio.to_thread(
            self._create_api_key_sync,
            label,
            scopes,
            allowed_targets,
            allowed_endpoints,
        )

    async def revoke_api_key(self, key_id: KeyId) -> bool:
        return await asyncio.to_thread(self._revoke_api_key_sync, key_id)

    async def list_api_keys(self) -> tuple[dict[str, object], ...]:
        return await asyncio.to_thread(self._list_api_keys_sync)

    async def resolve_request_identity(
        self, presented_key: str
    ) -> RequestIdentity | None:
        return await asyncio.to_thread(
            self._resolve_request_identity_sync, presented_key
        )

    async def grantable_scopes(self) -> frozenset[CapabilityName]:
        return self._grantable_scopes

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS targets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                fqdn TEXT NOT NULL UNIQUE,
                posture TEXT NOT NULL CHECK (posture = 'read_only'),
                is_prod INTEGER NOT NULL CHECK (is_prod IN (0, 1)),
                verify_ssl INTEGER NOT NULL CHECK (verify_ssl IN (0, 1)),
                auth_source TEXT NOT NULL,
                configuration_generation INTEGER NOT NULL,
                username_envelope TEXT NOT NULL,
                password_envelope TEXT NOT NULL,
                backend TEXT NOT NULL DEFAULT 'ops'
                    CHECK (backend IN ('ops', 'vcenter')),
                root_ca_envelope TEXT
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                digest BLOB NOT NULL,
                label TEXT NOT NULL,
                scopes_json TEXT NOT NULL,
                allowed_targets_json TEXT NOT NULL,
                allowed_endpoints_json TEXT NOT NULL DEFAULT '["ops","vcf"]',
                revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            );
            """
        )
        row = connection.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO schema_version(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        elif row[0] == 1:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN backend TEXT NOT NULL"
                    " DEFAULT 'ops' CHECK (backend IN ('ops', 'vcenter'))"
                )
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN root_ca_envelope TEXT"
                )
                connection.execute(
                    "ALTER TABLE api_keys ADD COLUMN allowed_endpoints_json TEXT"
                    ' NOT NULL DEFAULT \'["ops","vcf"]\''
                )
                connection.execute(
                    "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
                )
            except BaseException:
                connection.rollback()
                raise
        elif row[0] != SCHEMA_VERSION:
            raise RuntimeStoreUnavailable(
                f"unsupported runtime schema version {row[0]}"
            )
        connection.commit()

    def _load_or_create_keyring(self, *, refuse_generation: bool) -> None:
        if not self.keyring_path.exists():
            if refuse_generation:
                raise RuntimeStoreUnavailable(
                    "credential keyring is missing while encrypted targets exist"
                )
            key_id = secrets.token_hex(8)
            document = {
                "version": KEYRING_VERSION,
                "active_key_id": key_id,
                "keys": {
                    key_id: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(
                        "ascii"
                    )
                },
            }
            atomic_private_text_write(
                self.keyring_path,
                json.dumps(document, sort_keys=True, separators=(",", ":")),
            )

        raw = read_private_text(self.keyring_path)
        document = json.loads(raw)
        if document.get("version") != KEYRING_VERSION:
            raise RuntimeStoreUnavailable("unsupported credential keyring version")
        active = document.get("active_key_id")
        encoded_keys = document.get("keys")
        if not isinstance(active, str) or not isinstance(encoded_keys, dict):
            raise RuntimeStoreUnavailable("credential keyring is malformed")
        keys: dict[str, bytes] = {}
        for key_id, encoded in encoded_keys.items():
            if not isinstance(key_id, str) or not isinstance(encoded, str):
                raise RuntimeStoreUnavailable("credential keyring is malformed")
            value = base64.urlsafe_b64decode(encoded.encode("ascii"))
            if len(value) != 32:
                raise RuntimeStoreUnavailable("credential key has wrong length")
            keys[key_id] = value
        if active not in keys:
            raise RuntimeStoreUnavailable("active credential key is missing")
        self._active_key_id = active
        self._keys = keys

    def _connection_or_raise(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeStoreUnavailable("runtime repository is not open")
        return self._connection

    def _rollback_quietly(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.rollback()
        except sqlite3.Error:
            pass

    @contextlib.contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection_or_raise()
            try:
                yield connection
            except BaseException:
                self._rollback_quietly()
                raise

    def _is_ready_sync(self) -> bool:
        with self._write_transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('write_probe', CURRENT_TIMESTAMP)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value"
            )
            connection.commit()
            return True

    def _has_admin_sync(self) -> bool:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute("SELECT 1 FROM settings WHERE name = 'admin_password_hash'")
                .fetchone()
            )
            return row is not None

    def _initialize_admin_from_bootstrap_file_sync(self) -> bool:
        with self._lock:
            if self._has_admin_sync():
                self._remove_bootstrap_password_file_sync()
                return False
            try:
                password = read_private_text(self.bootstrap_password_path)
            except SecretStoreUnavailable:
                return False
            self._set_admin_password_sync(password)
            self._remove_bootstrap_password_file_sync()
            return True

    def _remove_bootstrap_password_file_sync(self) -> None:
        try:
            self.bootstrap_password_path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeStoreUnavailable(
                "admin password was stored but bootstrap file could not be removed"
            ) from exc

    def _set_admin_password_sync(self, password: str) -> None:
        if len(password.encode("utf-8")) < MINIMUM_ADMIN_PASSWORD_BYTES:
            raise ValueError("admin password must contain at least 16 bytes")
        with self._write_transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM settings WHERE name = 'admin_password_hash'"
            ).fetchone()
            if existing is not None:
                raise RuntimeStoreUnavailable("admin password is already initialized")
            connection.execute(
                "INSERT INTO settings(name, value) VALUES ('admin_password_hash', ?)",
                (hash_password(password),),
            )
            connection.commit()

    def _verify_admin_password_sync(self, password: str) -> bool:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT value FROM settings WHERE name = 'admin_password_hash'"
                )
                .fetchone()
            )
            return bool(row and verify_password(password, row[0]))

    def _get_sync(self, target_id: TargetId) -> TargetRecord | None:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute("SELECT * FROM targets WHERE id = ?", (str(target_id),))
                .fetchone()
            )
            return None if row is None else self._target_from_row(row)

    def _list_sync(self) -> tuple[TargetRecord, ...]:
        with self._lock:
            rows = (
                self._connection_or_raise()
                .execute("SELECT * FROM targets ORDER BY name, id")
                .fetchall()
            )
            return tuple(self._target_from_row(row) for row in rows)

    def _create_target_sync(
        self,
        name: str,
        fqdn: str,
        username: str,
        password: str,
        auth_source: str,
        verify_ssl: bool,
        backend: BackendKind | str,
        root_ca_pem: str | None,
    ) -> TargetRecord:
        normalized_fqdn = _normalize_fqdn(fqdn)
        if not name.strip() or not username or not password:
            raise ValueError("name, username, and password are required")
        normalized_source = auth_source.strip().upper() or "LOCAL"
        backend_kind = BackendKind(backend)
        normalized_ca = _normalize_root_ca(root_ca_pem)
        if verify_ssl and root_ca_pem is not None and normalized_ca is None:
            raise ValueError("the uploaded root CA bundle is empty")
        target_id = TargetId(str(uuid.uuid4()))
        is_prod = normalized_fqdn == PRODUCTION_FQDN
        target = TargetRecord(
            id=target_id,
            name=name.strip(),
            fqdn=normalized_fqdn,
            posture=TargetPosture.READ_ONLY,
            is_prod=is_prod,
            verify_ssl=verify_ssl,
            auth_source=normalized_source,
            configuration_generation=ConfigurationGeneration(1),
            backend=backend_kind,
            has_custom_ca=normalized_ca is not None,
        )
        username_envelope = self._encrypt(target_id, "username", username)
        password_envelope = self._encrypt(target_id, "password", password)
        root_ca_envelope = (
            self._encrypt(target_id, "root_ca", normalized_ca)
            if normalized_ca is not None
            else None
        )
        with self._write_transaction() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO targets(
                        id, name, fqdn, posture, is_prod, verify_ssl,
                        auth_source, configuration_generation,
                        username_envelope, password_envelope, backend,
                        root_ca_envelope
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(target.id),
                        target.name,
                        target.fqdn,
                        target.posture.value,
                        int(target.is_prod),
                        int(target.verify_ssl),
                        target.auth_source,
                        int(target.configuration_generation),
                        username_envelope,
                        password_envelope,
                        target.backend.value,
                        root_ca_envelope,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("a target with this FQDN already exists") from exc
        return target

    def _get_credentials_sync(self, target_id: TargetId) -> TargetCredentials:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT auth_source, username_envelope, password_envelope"
                    " FROM targets WHERE id = ?",
                    (str(target_id),),
                )
                .fetchone()
            )
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            username = self._decrypt(target_id, "username", row["username_envelope"])
            password = self._decrypt(target_id, "password", row["password_envelope"])
            return TargetCredentials(username, password, row["auth_source"])

    def _get_root_ca_sync(self, target_id: TargetId) -> str | None:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT root_ca_envelope FROM targets WHERE id = ?",
                    (str(target_id),),
                )
                .fetchone()
            )
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            envelope = row["root_ca_envelope"]
            if envelope is None:
                return None
            return self._decrypt(target_id, "root_ca", envelope)

    def _update_target_sync(
        self,
        target_id: TargetId,
        expected_generation: ConfigurationGeneration,
        name: str,
        fqdn: str,
        username: str | None,
        password: str | None,
        auth_source: str,
        verify_ssl: bool,
        posture: TargetPosture,
        root_ca_pem: str | None,
        clear_root_ca: bool,
    ) -> tuple[TargetRecord, TargetConfigurationChange]:
        normalized_fqdn = _normalize_fqdn(fqdn)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("target name is required")
        if posture is TargetPosture.ACTIONS_ENABLED:
            raise ValueError(
                "unsigned prototype packs cannot arm an actions-enabled target"
            )
        normalized_source = auth_source.strip().upper() or "LOCAL"
        normalized_ca = _normalize_root_ca(root_ca_pem)
        if root_ca_pem is not None and normalized_ca is None:
            raise ValueError("the uploaded root CA bundle is empty")

        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM targets WHERE id = ?", (str(target_id),)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            previous = ConfigurationGeneration(row["configuration_generation"])
            if previous != expected_generation:
                raise RuntimeStoreUnavailable("target configuration generation changed")
            current = ConfigurationGeneration(int(previous) + 1)
            username_envelope = row["username_envelope"]
            password_envelope = row["password_envelope"]
            root_ca_envelope = row["root_ca_envelope"]
            if username:
                username_envelope = self._encrypt(target_id, "username", username)
            if password:
                password_envelope = self._encrypt(target_id, "password", password)
            if clear_root_ca:
                root_ca_envelope = None
            elif normalized_ca is not None:
                root_ca_envelope = self._encrypt(target_id, "root_ca", normalized_ca)
            is_prod = normalized_fqdn == PRODUCTION_FQDN
            try:
                connection.execute(
                    """
                    UPDATE targets SET name = ?, fqdn = ?, posture = ?,
                        is_prod = ?, verify_ssl = ?, auth_source = ?,
                        configuration_generation = ?, username_envelope = ?,
                        password_envelope = ?, root_ca_envelope = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_name,
                        normalized_fqdn,
                        TargetPosture.READ_ONLY.value,
                        int(is_prod),
                        int(verify_ssl),
                        normalized_source,
                        int(current),
                        username_envelope,
                        password_envelope,
                        root_ca_envelope,
                        str(target_id),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("a target with this FQDN already exists") from exc
            stored = self._target_from_row(
                connection.execute(
                    "SELECT * FROM targets WHERE id = ?", (str(target_id),)
                ).fetchone()
            )
            return stored, TargetConfigurationChange(target_id, previous, current)

    def _save_sync(
        self,
        target: TargetRecord,
        expected_generation: ConfigurationGeneration | None,
    ) -> TargetConfigurationChange:
        if target.posture is not TargetPosture.READ_ONLY:
            raise ValueError(
                "unsigned prototype packs cannot arm an actions-enabled target"
            )
        normalized_fqdn = _normalize_fqdn(target.fqdn)
        if target.is_prod != (normalized_fqdn == PRODUCTION_FQDN):
            raise ValueError("production identity is derived from its FQDN")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT configuration_generation FROM targets WHERE id = ?",
                (str(target.id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target.id}")
            previous = ConfigurationGeneration(row[0])
            if expected_generation is not None and previous != expected_generation:
                raise RuntimeStoreUnavailable("target configuration generation changed")
            current = ConfigurationGeneration(int(previous) + 1)
            connection.execute(
                """
                UPDATE targets SET name = ?, fqdn = ?, posture = ?,
                    is_prod = ?, verify_ssl = ?, auth_source = ?,
                    configuration_generation = ?
                WHERE id = ?
                """,
                (
                    target.name,
                    normalized_fqdn,
                    TargetPosture.READ_ONLY.value,
                    int(target.is_prod),
                    int(target.verify_ssl),
                    target.auth_source,
                    int(current),
                    str(target.id),
                ),
            )
            connection.commit()
            return TargetConfigurationChange(target.id, previous, current)

    def _create_api_key_sync(
        self,
        label: str,
        scopes: frozenset[CapabilityName],
        allowed_targets: frozenset[TargetId],
        allowed_endpoints: frozenset[str] | None,
    ) -> str:
        if not label.strip():
            raise ValueError("API key label is required")
        if not scopes or not scopes.issubset(self._grantable_scopes):
            raise ValueError("API key scopes must be implemented capabilities")
        if not allowed_targets:
            raise ValueError("at least one target must be allowed")
        with self._write_transaction() as connection:
            placeholders = ",".join("?" for _ in allowed_targets)
            found = connection.execute(
                f"SELECT id FROM targets WHERE id IN ({placeholders})",
                tuple(str(value) for value in allowed_targets),
            ).fetchall()
            if {row[0] for row in found} != {str(value) for value in allowed_targets}:
                raise ValueError("API key names an unknown target")
            backend_rows = connection.execute(
                f"SELECT backend FROM targets WHERE id IN ({placeholders})",
                tuple(str(value) for value in allowed_targets),
            ).fetchall()
            target_endpoints = frozenset(row[0] for row in backend_rows)
            endpoints = allowed_endpoints or (target_endpoints | {"vcf"})
            known_endpoints = frozenset({*(kind.value for kind in BackendKind), "vcf"})
            if not endpoints or not endpoints.issubset(known_endpoints):
                raise ValueError("API key endpoints must be registered backends")
            if not target_endpoints.issubset(endpoints):
                raise ValueError(
                    "every allowed target must belong to an allowed endpoint"
                )
            key_id = KeyId(secrets.token_hex(8))
            presented = f"vok_{key_id}_{secrets.token_urlsafe(32)}"
            digest = hashlib.sha256(presented.encode("utf-8")).digest()
            connection.execute(
                """
                INSERT INTO api_keys(
                    key_id, digest, label, scopes_json, allowed_targets_json
                    , allowed_endpoints_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(key_id),
                    digest,
                    label.strip(),
                    json.dumps(sorted(str(value) for value in scopes)),
                    json.dumps(sorted(str(value) for value in allowed_targets)),
                    json.dumps(sorted(endpoints)),
                ),
            )
            connection.commit()
            return presented

    def _revoke_api_key_sync(self, key_id: KeyId) -> bool:
        with self._write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET revoked = 1,"
                " revoked_at = CURRENT_TIMESTAMP"
                " WHERE key_id = ? AND revoked = 0",
                (str(key_id),),
            )
            connection.commit()
            return cursor.rowcount == 1

    def _list_api_keys_sync(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            rows = (
                self._connection_or_raise()
                .execute(
                    "SELECT key_id, label, scopes_json, allowed_targets_json,"
                    " allowed_endpoints_json, revoked, created_at, revoked_at"
                    " FROM api_keys ORDER BY created_at DESC, key_id"
                )
                .fetchall()
            )
            return tuple(
                {
                    "key_id": row["key_id"],
                    "label": row["label"],
                    "scopes": json.loads(row["scopes_json"]),
                    "allowed_targets": json.loads(row["allowed_targets_json"]),
                    "allowed_endpoints": json.loads(row["allowed_endpoints_json"]),
                    "revoked": bool(row["revoked"]),
                    "created_at": row["created_at"],
                    "revoked_at": row["revoked_at"],
                }
                for row in rows
            )

    def _resolve_request_identity_sync(
        self, presented_key: str
    ) -> RequestIdentity | None:
        parts = presented_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "vok" or not parts[1] or not parts[2]:
            return None
        key_id = KeyId(parts[1])
        candidate = hashlib.sha256(presented_key.encode("utf-8")).digest()
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT digest, scopes_json, allowed_targets_json,"
                    " allowed_endpoints_json, revoked"
                    " FROM api_keys WHERE key_id = ?",
                    (str(key_id),),
                )
                .fetchone()
            )
            if row is None or not secrets.compare_digest(candidate, row["digest"]):
                return None
            scopes = frozenset(json.loads(row["scopes_json"]))
            targets = frozenset(
                TargetId(value) for value in json.loads(row["allowed_targets_json"])
            )
            return RequestIdentity(
                key_id=key_id,
                granted_scopes=scopes,
                allowed_targets=targets,
                revoked=bool(row["revoked"]),
                allowed_endpoints=frozenset(json.loads(row["allowed_endpoints_json"])),
            )

    def _target_from_row(self, row: sqlite3.Row) -> TargetRecord:
        return TargetRecord(
            id=TargetId(row["id"]),
            name=row["name"],
            fqdn=row["fqdn"],
            posture=TargetPosture(row["posture"]),
            is_prod=bool(row["is_prod"]),
            verify_ssl=bool(row["verify_ssl"]),
            auth_source=row["auth_source"],
            configuration_generation=ConfigurationGeneration(
                row["configuration_generation"]
            ),
            backend=BackendKind(row["backend"]),
            has_custom_ca=row["root_ca_envelope"] is not None,
        )

    def _encrypt(self, target_id: TargetId, purpose: str, value: str) -> str:
        if self._active_key_id is None:
            raise RuntimeStoreUnavailable("credential keyring is not loaded")
        nonce = secrets.token_bytes(12)
        aad = self._aad(target_id, purpose, self._active_key_id)
        ciphertext = AESGCM(self._keys[self._active_key_id]).encrypt(
            nonce, value.encode("utf-8"), aad
        )
        return json.dumps(
            {
                "version": 1,
                "key_id": self._active_key_id,
                "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _decrypt(self, target_id: TargetId, purpose: str, envelope: str) -> str:
        try:
            document = json.loads(envelope)
            key_id = document["key_id"]
            if document["version"] != 1 or key_id not in self._keys:
                raise ValueError
            nonce = base64.urlsafe_b64decode(document["nonce"])
            ciphertext = base64.urlsafe_b64decode(document["ciphertext"])
            plaintext = AESGCM(self._keys[key_id]).decrypt(
                nonce,
                ciphertext,
                self._aad(target_id, purpose, key_id),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, KeyError, ValueError, UnicodeDecodeError) as exc:
            raise RuntimeStoreUnavailable(
                f"credential envelope failed integrity for target {target_id}"
            ) from exc

    @staticmethod
    def _aad(target_id: TargetId, purpose: str, key_id: str) -> bytes:
        return (
            f"schema={ENVELOPE_SCHEMA_VERSION}|target={target_id}|"
            f"purpose={purpose}|key={key_id}"
        ).encode("utf-8")


def _normalize_fqdn(value: str) -> str:
    normalized = value.strip().rstrip(".").lower()
    if not _FQDN.fullmatch(normalized):
        raise ValueError("FQDN must be a hostname without a scheme or path")
    return normalized


def _normalize_root_ca(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized.encode("utf-8")) > 256 * 1024:
        raise ValueError("root CA bundle exceeds the 256 KiB limit")
    try:
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=normalized)
    except ssl.SSLError as exc:
        raise ValueError("root CA bundle is not valid PEM certificate data") from exc
    return normalized + "\n"
