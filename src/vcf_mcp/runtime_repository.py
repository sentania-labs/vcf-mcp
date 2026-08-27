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
import logging
import os
import re
import secrets
import sqlite3
import ssl
import threading
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vcf_mcp.admin.auth import hash_password, verify_password
from vcf_mcp.contracts import (
    AuthorizationMode,
    BackendKind,
    CapabilityName,
    ConfigurationGeneration,
    EffectiveTargetTrust,
    KeyId,
    RequestIdentity,
    TargetConfigurationChange,
    TargetId,
    TargetPosture,
    TargetRecord,
)
from vcf_mcp.security import (
    SecretStoreUnavailable,
    atomic_private_text_write,
    read_private_text,
)
from vcf_mcp.vcf.client import TargetCredentials

DEFAULT_CONFIG_DB_PATH = Path("/data/config.sqlite3")
DEFAULT_CREDENTIAL_KEYRING_PATH = Path("/keys/credential_keyring.json")
DEFAULT_ADMIN_BOOTSTRAP_PASSWORD_FILE = Path("/keys/admin_bootstrap_password")
PRODUCTION_FQDN = "vcf-lab-operations.int.sentania.net"
SCHEMA_VERSION = 7
ENVELOPE_SCHEMA_VERSION = 2
KEYRING_VERSION = 1
MINIMUM_ADMIN_PASSWORD_BYTES = 16
AUTH_FAILURE_LIMIT = 3
LOGGER = logging.getLogger(__name__)
_FQDN = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_PEM_BLOCK = re.compile(
    r"-----BEGIN ([A-Z0-9][A-Z0-9 ]*)-----.*?-----END \1-----", re.DOTALL
)


def global_ca_target_digest(
    targets: tuple[TargetRecord, ...], certificate_fingerprints: tuple[str, ...]
) -> str:
    displayed = sorted(
        (str(target.id), target.name, target.fqdn, target.has_custom_ca)
        for target in targets
    )
    encoded = json.dumps(
        (displayed, certificate_fingerprints),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RuntimeStoreUnavailable(RuntimeError):
    """Raised when runtime configuration cannot be used safely."""


class GlobalRootCaTargetSetChanged(ValueError):
    """Raised when global CA removal confirmation is stale."""


class AllTargetsIntegrityFailed(RuntimeStoreUnavailable):
    """Raised when no configured backend has a valid credential envelope."""


@dataclass(frozen=True, slots=True)
class TargetVerificationMaterial:
    """Submitted target configuration held only long enough to verify it."""

    target: TargetRecord
    credentials: TargetCredentials
    target_root_ca_pem: str | None


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
                self._verify_target_integrity_at_startup()
            except AllTargetsIntegrityFailed:
                self.close()
                raise
            except (
                OSError,
                sqlite3.Error,
                SecretStoreUnavailable,
                RuntimeStoreUnavailable,
                ValueError,
            ) as exc:
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

    async def initialize_admin(self, password: str) -> None:
        """Hash a first-run password supplied by the onboarding interface."""

        await asyncio.to_thread(self._set_admin_password_sync, password)

    async def verify_admin_password(self, password: str) -> bool:
        return await asyncio.to_thread(self._verify_admin_password_sync, password)

    async def get(self, target_id: TargetId) -> TargetRecord | None:
        return await asyncio.to_thread(self._get_sync, target_id)

    async def list(self) -> tuple[TargetRecord, ...]:
        return await asyncio.to_thread(self._list_sync)

    def list_at_startup(self) -> tuple[TargetRecord, ...]:
        """Read startup wiring before the ASGI event loop begins."""

        return self._list_usable_sync()

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
        target_id: TargetId | None = None,
        last_verified_at: datetime | None = None,
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
            target_id,
            last_verified_at,
        )

    async def prepare_target_registration(
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
    ) -> TargetVerificationMaterial:
        return await asyncio.to_thread(
            self._prepare_target_registration_sync,
            name,
            fqdn,
            username,
            password,
            auth_source,
            verify_ssl,
            backend,
            root_ca_pem,
            None,
        )

    async def get_credentials(self, target_id: TargetId) -> TargetCredentials:
        return await asyncio.to_thread(self._get_credentials_sync, target_id)

    async def get_root_ca(self, target_id: TargetId) -> str | None:
        return await asyncio.to_thread(self._get_root_ca_sync, target_id)

    async def get_global_root_ca(self) -> str | None:
        return await asyncio.to_thread(self._get_global_root_ca_sync)

    async def get_global_root_ca_fingerprints(self) -> tuple[str, ...]:
        return await asyncio.to_thread(self._get_global_root_ca_fingerprints_sync)

    async def get_effective_trust(
        self, target_id: TargetId
    ) -> EffectiveTargetTrust:
        """Resolve global plus per-target trust without contacting the target."""

        return await asyncio.to_thread(self._get_effective_trust_sync, target_id)

    async def set_global_root_ca(self, root_ca_pem: str) -> str:
        """Set or replace the appliance CA and return the audited action name."""

        return await asyncio.to_thread(self._set_global_root_ca_sync, root_ca_pem)

    async def remove_global_root_ca(
        self, expected_target_digest: str
    ) -> tuple[TargetRecord, ...]:
        """Remove appliance trust and return the targets that lost that trust."""

        return await asyncio.to_thread(
            self._remove_global_root_ca_sync, expected_target_digest
        )

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
        last_verified_at: datetime | None = None,
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
            last_verified_at,
        )

    async def prepare_target_update(
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
    ) -> TargetVerificationMaterial:
        return await asyncio.to_thread(
            self._prepare_target_update_sync,
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

    async def mark_target_verified(
        self,
        target_id: TargetId,
        *,
        expected_generation: ConfigurationGeneration,
        verified_at: datetime,
    ) -> TargetRecord:
        return await asyncio.to_thread(
            self._mark_target_verified_sync,
            target_id,
            expected_generation,
            verified_at,
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

    def set_grantable_scopes_at_startup(
        self, scopes: frozenset[CapabilityName]
    ) -> None:
        self._grantable_scopes = scopes

    def set_pack_action_trust_at_startup(self, trusted: bool) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('all_active_packs_trusted', ?)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                ("1" if trusted else "0",),
            )
            connection.commit()

    async def authorization_mode(self) -> AuthorizationMode:
        return await asyncio.to_thread(self._authorization_mode_sync)

    async def set_authorization_mode(self, mode: AuthorizationMode | str) -> int:
        return await asyncio.to_thread(self._set_authorization_mode_sync, mode)

    async def clear_auth_lockout(self, target_id: TargetId) -> bool:
        return await asyncio.to_thread(self._clear_auth_lockout_sync, target_id)

    async def record_auth_failure(self, target_id: TargetId) -> bool:
        return await asyncio.to_thread(self._record_auth_failure_sync, target_id)

    async def record_auth_success(self, target_id: TargetId) -> None:
        await asyncio.to_thread(self._record_auth_success_sync, target_id)

    async def rotate_credential_key(
        self, *, batch_size: int = 25, start_new: bool = False
    ) -> dict[str, int | str]:
        return await asyncio.to_thread(
            self._rotate_credential_key_sync, batch_size, start_new
        )

    async def rotation_status(self) -> dict[str, int | str] | None:
        return await asyncio.to_thread(self._rotation_status_sync)

    async def configuration_events(
        self, *, limit: int = 100
    ) -> tuple[dict[str, object], ...]:
        return await asyncio.to_thread(self._configuration_events_sync, limit)

    async def backup_database(self, destination: Path) -> Path:
        """Write a database-only backup that cannot target the keyring volume."""

        return await asyncio.to_thread(self._backup_database_sync, destination)

    async def unsigned_packs_allowed(self) -> bool:
        return await asyncio.to_thread(self._unsigned_packs_allowed_sync)

    def unsigned_packs_allowed_at_startup(self) -> bool:
        return self._unsigned_packs_allowed_sync()

    async def set_unsigned_packs_allowed(self, allowed: bool) -> None:
        await asyncio.to_thread(self._set_unsigned_packs_allowed_sync, allowed)

    async def restart_required(self) -> bool:
        return await asyncio.to_thread(self._restart_required_sync)

    def set_restart_required_at_startup(self, required: bool) -> None:
        self._set_restart_required_sync(required)

    async def has_actions_enabled_target(self) -> bool:
        return await asyncio.to_thread(self._has_actions_enabled_target_sync)

    def has_actions_enabled_target_at_startup(self) -> bool:
        return self._has_actions_enabled_target_sync()

    async def record_configuration_event(
        self, event_type: str, details: Mapping[str, object]
    ) -> None:
        await asyncio.to_thread(
            self._record_configuration_event_sync, event_type, details
        )

    def record_configuration_event_at_startup(
        self, event_type: str, details: Mapping[str, object]
    ) -> None:
        self._record_configuration_event_sync(event_type, details)

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
                posture TEXT NOT NULL
                    CHECK (posture IN ('read_only', 'actions_enabled')),
                is_prod INTEGER NOT NULL CHECK (is_prod IN (0, 1)),
                verify_ssl INTEGER NOT NULL CHECK (verify_ssl IN (0, 1)),
                auth_source TEXT NOT NULL,
                configuration_generation INTEGER NOT NULL,
                username_envelope TEXT NOT NULL,
                password_envelope TEXT NOT NULL,
                backend TEXT NOT NULL DEFAULT 'ops'
                    CHECK (backend IN (
                        'ops', 'vcenter', 'nsx', 'sddc-manager', 'ops-networks',
                        'fleet-lcm', 'sddc-lcm', 'log-management', 'vsan-dp',
                        'avi', 'automation', 'identity-broker', 'software-depot'
                )),
                root_ca_envelope TEXT,
                unusable_reason TEXT,
                auth_failure_count INTEGER NOT NULL DEFAULT 0,
                auth_locked INTEGER NOT NULL DEFAULT 0
                    CHECK (auth_locked IN (0, 1)),
                last_verified_at TEXT
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                digest BLOB NOT NULL,
                label TEXT NOT NULL,
                scopes_json TEXT NOT NULL,
                allowed_targets_json TEXT NOT NULL,
                allowed_endpoints_json TEXT NOT NULL DEFAULT '["ops","vcf"]',
                authorization_mode TEXT NOT NULL DEFAULT 'local'
                    CHECK (authorization_mode IN ('local', 'gateway')),
                revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS credential_rotation (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                old_key_id TEXT NOT NULL,
                new_key_id TEXT NOT NULL,
                last_target_id TEXT,
                rotated_targets INTEGER NOT NULL DEFAULT 0,
                total_targets INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('running', 'complete'))
            );
            CREATE TABLE IF NOT EXISTS configuration_events (
                id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                    " DEFAULT 'ops' CHECK (backend IN ("
                    "'ops','vcenter','nsx','sddc-manager','ops-networks',"
                    "'fleet-lcm','sddc-lcm','log-management','vsan-dp',"
                    "'avi','automation','identity-broker','software-depot'))"
                )
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN root_ca_envelope TEXT"
                )
                connection.execute(
                    "ALTER TABLE api_keys ADD COLUMN allowed_endpoints_json TEXT"
                    ' NOT NULL DEFAULT \'["ops","vcf"]\''
                )
                connection.execute("UPDATE schema_version SET version = 3")
            except BaseException:
                connection.rollback()
                raise
        elif row[0] == 2:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE targets_v3 (
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
                            CHECK (backend IN (
                                'ops', 'vcenter', 'nsx', 'sddc-manager',
                                'ops-networks', 'fleet-lcm', 'sddc-lcm',
                                'log-management', 'vsan-dp', 'avi', 'automation',
                                'identity-broker', 'software-depot'
                            )),
                        root_ca_envelope TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO targets_v3(
                        id, name, fqdn, posture, is_prod, verify_ssl,
                        auth_source, configuration_generation,
                        username_envelope, password_envelope, backend,
                        root_ca_envelope
                    )
                    SELECT
                        id, name, fqdn, posture, is_prod, verify_ssl,
                        auth_source, configuration_generation,
                        username_envelope, password_envelope, backend,
                        root_ca_envelope
                    FROM targets
                    """
                )
                connection.execute("DROP TABLE targets")
                connection.execute("ALTER TABLE targets_v3 RENAME TO targets")
                connection.execute("UPDATE schema_version SET version = 3")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        elif row[0] not in (3, 4, 5, 6, SCHEMA_VERSION):
            raise RuntimeStoreUnavailable(
                f"unsupported runtime schema version {row[0]}"
            )
        current = connection.execute("SELECT version FROM schema_version").fetchone()[0]
        if current < 4:
            target_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(targets)")
            }
            if "unusable_reason" not in target_columns:
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN unusable_reason TEXT"
                )
            if "auth_failure_count" not in target_columns:
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN auth_failure_count INTEGER"
                    " NOT NULL DEFAULT 0"
                )
            if "auth_locked" not in target_columns:
                connection.execute(
                    "ALTER TABLE targets ADD COLUMN auth_locked INTEGER"
                    " NOT NULL DEFAULT 0 CHECK (auth_locked IN (0, 1))"
                )
            api_key_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(api_keys)")
            }
            if "authorization_mode" not in api_key_columns:
                connection.execute(
                    "ALTER TABLE api_keys ADD COLUMN authorization_mode TEXT"
                    " NOT NULL DEFAULT 'local'"
                    " CHECK (authorization_mode IN ('local', 'gateway'))"
                )
            current = 4
        if current < 5:
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('authorization_mode', 'local') ON CONFLICT(name) DO NOTHING"
            )
            current = 5
        if current < SCHEMA_VERSION:
            connection.execute(
                """
                CREATE TABLE targets_v7 (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    fqdn TEXT NOT NULL UNIQUE,
                    posture TEXT NOT NULL
                        CHECK (posture IN ('read_only', 'actions_enabled')),
                    is_prod INTEGER NOT NULL CHECK (is_prod IN (0, 1)),
                    verify_ssl INTEGER NOT NULL CHECK (verify_ssl IN (0, 1)),
                    auth_source TEXT NOT NULL,
                    configuration_generation INTEGER NOT NULL,
                    username_envelope TEXT NOT NULL,
                    password_envelope TEXT NOT NULL,
                    backend TEXT NOT NULL CHECK (backend IN (
                        'ops', 'vcenter', 'nsx', 'sddc-manager', 'ops-networks',
                        'fleet-lcm', 'sddc-lcm', 'log-management', 'vsan-dp',
                        'avi', 'automation', 'identity-broker', 'software-depot'
                    )),
                    root_ca_envelope TEXT,
                    unusable_reason TEXT,
                    auth_failure_count INTEGER NOT NULL DEFAULT 0,
                    auth_locked INTEGER NOT NULL DEFAULT 0
                        CHECK (auth_locked IN (0, 1)),
                    last_verified_at TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO targets_v7 SELECT
                    id, name, fqdn, posture, is_prod, verify_ssl, auth_source,
                    configuration_generation, username_envelope,
                    password_envelope, backend, root_ca_envelope,
                    unusable_reason, auth_failure_count, auth_locked, NULL
                FROM targets
                """
            )
            connection.execute("DROP TABLE targets")
            connection.execute("ALTER TABLE targets_v7 RENAME TO targets")
            current = SCHEMA_VERSION
        connection.execute("UPDATE schema_version SET version = ?", (current,))
        connection.execute(
            "INSERT INTO settings(name, value) VALUES"
            " ('authorization_mode', 'local') ON CONFLICT(name) DO NOTHING"
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
        self._retire_keys_after_completed_rotation()

    def _write_keyring(self) -> None:
        if self._active_key_id is None:
            raise RuntimeStoreUnavailable("credential keyring is not loaded")
        document = {
            "version": KEYRING_VERSION,
            "active_key_id": self._active_key_id,
            "keys": {
                key_id: base64.urlsafe_b64encode(value).decode("ascii")
                for key_id, value in sorted(self._keys.items())
            },
        }
        atomic_private_text_write(
            self.keyring_path,
            json.dumps(document, sort_keys=True, separators=(",", ":")),
        )

    def _verify_target_integrity_at_startup(self) -> None:
        connection = self._connection_or_raise()
        rows = connection.execute("SELECT * FROM targets ORDER BY id").fetchall()
        if not rows:
            return
        usable = 0
        for row in rows:
            target_id = TargetId(row["id"])
            try:
                self._decrypt(target_id, "username", row["username_envelope"])
                self._decrypt(target_id, "password", row["password_envelope"])
                if row["root_ca_envelope"] is not None:
                    self._decrypt(target_id, "root_ca", row["root_ca_envelope"])
            except RuntimeStoreUnavailable:
                connection.execute(
                    "UPDATE targets SET unusable_reason = ? WHERE id = ?",
                    ("credential_integrity_failure", str(target_id)),
                )
                LOGGER.error(
                    "target %s is unusable because credential integrity failed",
                    target_id,
                )
            else:
                usable += 1
                connection.execute(
                    "UPDATE targets SET unusable_reason = NULL WHERE id = ?",
                    (str(target_id),),
                )
        connection.commit()
        if usable == 0:
            raise AllTargetsIntegrityFailed(
                "every configured target failed credential integrity verification"
            )

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

    def _list_usable_sync(self) -> tuple[TargetRecord, ...]:
        return tuple(target for target in self._list_sync() if target.is_usable)

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
        target_id: TargetId | None,
        last_verified_at: datetime | None,
    ) -> TargetRecord:
        material = self._prepare_target_registration_sync(
            name,
            fqdn,
            username,
            password,
            auth_source,
            verify_ssl,
            backend,
            root_ca_pem,
            target_id,
        )
        target = material.target
        target = replace(target, last_verified_at=last_verified_at)
        username, password = material.credentials.basic_auth_tuple()
        normalized_ca = material.target_root_ca_pem
        username_envelope = self._encrypt(target.id, "username", username)
        password_envelope = self._encrypt(target.id, "password", password)
        root_ca_envelope = (
            self._encrypt(target.id, "root_ca", normalized_ca)
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
                        root_ca_envelope, last_verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        (
                            None
                            if target.last_verified_at is None
                            else target.last_verified_at.isoformat()
                        ),
                    ),
                )
                connection.execute(
                    "INSERT INTO settings(name, value) VALUES"
                    " ('restart_required', '1')"
                    " ON CONFLICT(name) DO UPDATE SET value = excluded.value"
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("a target with this FQDN already exists") from exc
        return target

    def _prepare_target_registration_sync(
        self,
        name: str,
        fqdn: str,
        username: str,
        password: str,
        auth_source: str,
        verify_ssl: bool,
        backend: BackendKind | str,
        root_ca_pem: str | None,
        target_id: TargetId | None,
    ) -> TargetVerificationMaterial:
        normalized_fqdn = _normalize_fqdn(fqdn)
        if not name.strip() or not username or not password:
            raise ValueError("name, username, and password are required")
        normalized_source = auth_source.strip().upper() or "LOCAL"
        backend_kind = BackendKind(backend)
        normalized_ca = _normalize_root_ca(root_ca_pem)
        if verify_ssl and root_ca_pem is not None and normalized_ca is None:
            raise ValueError("the uploaded root CA bundle is empty")
        selected_target_id = target_id or TargetId(str(uuid.uuid4()))
        is_prod = normalized_fqdn == PRODUCTION_FQDN
        target = TargetRecord(
            id=selected_target_id,
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
        return TargetVerificationMaterial(
            target=target,
            credentials=TargetCredentials(username, password, normalized_source),
            target_root_ca_pem=normalized_ca,
        )

    def _get_credentials_sync(self, target_id: TargetId) -> TargetCredentials:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT auth_source, username_envelope, password_envelope,"
                    " unusable_reason, auth_locked"
                    " FROM targets WHERE id = ?",
                    (str(target_id),),
                )
                .fetchone()
            )
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            if row["unusable_reason"] is not None:
                raise RuntimeStoreUnavailable(
                    f"target {target_id} is unusable due to stored credential integrity"
                )
            if row["auth_locked"]:
                raise RuntimeStoreUnavailable(
                    f"target {target_id} authentication is locked pending operator reset"
                )
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

    def _get_global_root_ca_sync(self) -> str | None:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT value FROM settings WHERE name = 'global_root_ca_pem'"
                )
                .fetchone()
            )
            return None if row is None else str(row[0])

    def _get_global_root_ca_fingerprints_sync(self) -> tuple[str, ...]:
        return _certificate_fingerprints(self._get_global_root_ca_sync())

    def _get_effective_trust_sync(
        self, target_id: TargetId
    ) -> EffectiveTargetTrust:
        global_ca = self._get_global_root_ca_sync()
        target = self._get_sync(target_id)
        if target is None:
            raise KeyError(f"unknown target: {target_id}")
        target_ca_available = True
        try:
            target_ca = self._get_root_ca_sync(target_id)
        except RuntimeStoreUnavailable:
            if target.is_usable:
                raise
            target_ca = None
            target_ca_available = False
        bundle_parts = tuple(value for value in (global_ca, target_ca) if value)
        return EffectiveTargetTrust(
            root_ca_pem="".join(bundle_parts) or None,
            global_ca_fingerprints=_certificate_fingerprints(global_ca),
            target_ca_fingerprints=_certificate_fingerprints(target_ca),
            global_ca_configured=global_ca is not None,
            target_ca_configured=target.has_custom_ca,
            target_ca_available=target_ca_available,
        )

    def _set_global_root_ca_sync(self, root_ca_pem: str) -> str:
        normalized = _normalize_root_ca(root_ca_pem)
        if normalized is None:
            raise ValueError("the uploaded appliance root CA bundle is empty")
        with self._write_transaction() as connection:
            previous = connection.execute(
                "SELECT value FROM settings WHERE name = 'global_root_ca_pem'"
            ).fetchone()
            event_type = (
                "global_root_ca_set" if previous is None else "global_root_ca_replaced"
            )
            previous_ca = None if previous is None else str(previous[0])
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('global_root_ca_pem', ?)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (normalized,),
            )
            targets = self._list_sync()
            self._append_configuration_event_sync(
                connection,
                event_type,
                {
                    "certificate_fingerprints": list(
                        _certificate_fingerprints(normalized)
                    ),
                    "previous_certificate_fingerprints": list(
                        _certificate_fingerprints(previous_ca)
                    ),
                    "affected_targets": [target.name for target in targets],
                },
            )
            connection.commit()
            return event_type

    def _remove_global_root_ca_sync(
        self, expected_target_digest: str
    ) -> tuple[TargetRecord, ...]:
        with self._write_transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT value FROM settings WHERE name = 'global_root_ca_pem'"
            ).fetchone()
            if previous is None:
                connection.commit()
                return ()
            rows = connection.execute(
                "SELECT * FROM targets ORDER BY name, id"
            ).fetchall()
            targets = tuple(self._target_from_row(row) for row in rows)
            if not secrets.compare_digest(
                expected_target_digest,
                global_ca_target_digest(
                    targets, _certificate_fingerprints(str(previous[0]))
                ),
            ):
                raise GlobalRootCaTargetSetChanged(
                    "the affected target set changed since this page loaded"
                )
            connection.execute(
                "DELETE FROM settings WHERE name = 'global_root_ca_pem'"
            )
            self._append_configuration_event_sync(
                connection,
                "global_root_ca_removed",
                {
                    "removed_certificate_fingerprints": list(
                        _certificate_fingerprints(str(previous[0]))
                    ),
                    "affected_targets": [target.name for target in targets],
                },
            )
            connection.commit()
            return targets

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
        last_verified_at: datetime | None,
    ) -> tuple[TargetRecord, TargetConfigurationChange]:
        material = self._prepare_target_update_sync(
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
        target = replace(material.target, last_verified_at=last_verified_at)
        selected_username, selected_password = material.credentials.basic_auth_tuple()
        username_envelope = self._encrypt(target_id, "username", selected_username)
        password_envelope = self._encrypt(target_id, "password", selected_password)
        root_ca_envelope = (
            None
            if material.target_root_ca_pem is None
            else self._encrypt(
                target_id, "root_ca", material.target_root_ca_pem
            )
        )
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT configuration_generation FROM targets WHERE id = ?",
                (str(target_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            previous = ConfigurationGeneration(row["configuration_generation"])
            if previous != expected_generation:
                raise RuntimeStoreUnavailable("target configuration generation changed")
            try:
                connection.execute(
                    """
                    UPDATE targets SET name = ?, fqdn = ?, posture = ?,
                        is_prod = ?, verify_ssl = ?, auth_source = ?,
                        configuration_generation = ?, username_envelope = ?,
                        password_envelope = ?, root_ca_envelope = ?,
                        unusable_reason = NULL, last_verified_at = ?
                    WHERE id = ?
                    """,
                    (
                        target.name,
                        target.fqdn,
                        target.posture.value,
                        int(target.is_prod),
                        int(target.verify_ssl),
                        target.auth_source,
                        int(target.configuration_generation),
                        username_envelope,
                        password_envelope,
                        root_ca_envelope,
                        (
                            None
                            if target.last_verified_at is None
                            else target.last_verified_at.isoformat()
                        ),
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
            return stored, TargetConfigurationChange(
                target_id, previous, target.configuration_generation
            )

    def _prepare_target_update_sync(
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
    ) -> TargetVerificationMaterial:
        normalized_fqdn = _normalize_fqdn(fqdn)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("target name is required")
        if posture is TargetPosture.ACTIONS_ENABLED:
            if normalized_fqdn == PRODUCTION_FQDN:
                raise ValueError(
                    "the production appliance is hard-blocked from actions"
                )
            if not self._all_active_packs_trusted_sync():
                raise ValueError(
                    "actions require every active backend pack to be trusted"
                )
        normalized_source = auth_source.strip().upper() or "LOCAL"
        normalized_ca = _normalize_root_ca(root_ca_pem)
        if root_ca_pem is not None and normalized_ca is None:
            raise ValueError("the uploaded root CA bundle is empty")

        with self._lock:
            connection = self._connection_or_raise()
            row = connection.execute(
                "SELECT * FROM targets WHERE id = ?", (str(target_id),)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            previous = ConfigurationGeneration(row["configuration_generation"])
            if previous != expected_generation:
                raise RuntimeStoreUnavailable("target configuration generation changed")
            if row["auth_locked"]:
                raise RuntimeStoreUnavailable(
                    "target authentication is locked pending operator reset"
                )
            current = ConfigurationGeneration(int(previous) + 1)
            if row["unusable_reason"] is not None and (not username or not password):
                raise ValueError(
                    "an integrity-failed target requires both credentials to recover"
                )
            selected_username = username or self._decrypt(
                target_id, "username", row["username_envelope"]
            )
            selected_password = password or self._decrypt(
                target_id, "password", row["password_envelope"]
            )
            if clear_root_ca:
                selected_root_ca = None
            elif normalized_ca is not None:
                selected_root_ca = normalized_ca
            elif row["root_ca_envelope"] is None:
                selected_root_ca = None
            else:
                try:
                    selected_root_ca = self._decrypt(
                        target_id, "root_ca", row["root_ca_envelope"]
                    )
                except RuntimeStoreUnavailable as exc:
                    raise ValueError(
                        "target remains quarantined: the stored root CA must be"
                        " replaced or removed"
                    ) from exc
            is_prod = normalized_fqdn == PRODUCTION_FQDN
            return TargetVerificationMaterial(
                target=TargetRecord(
                    id=target_id,
                    name=normalized_name,
                    fqdn=normalized_fqdn,
                    posture=posture,
                    is_prod=is_prod,
                    verify_ssl=verify_ssl,
                    auth_source=normalized_source,
                    configuration_generation=current,
                    backend=BackendKind(row["backend"]),
                    has_custom_ca=selected_root_ca is not None,
                    last_verified_at=(
                        None
                        if row["last_verified_at"] is None
                        else datetime.fromisoformat(row["last_verified_at"])
                    ),
                ),
                credentials=TargetCredentials(
                    selected_username, selected_password, normalized_source
                ),
                target_root_ca_pem=selected_root_ca,
            )

    def _mark_target_verified_sync(
        self,
        target_id: TargetId,
        expected_generation: ConfigurationGeneration,
        verified_at: datetime,
    ) -> TargetRecord:
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT configuration_generation FROM targets WHERE id = ?",
                (str(target_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            if ConfigurationGeneration(row[0]) != expected_generation:
                raise RuntimeStoreUnavailable("target configuration generation changed")
            connection.execute(
                "UPDATE targets SET last_verified_at = ? WHERE id = ?",
                (verified_at.isoformat(), str(target_id)),
            )
            connection.commit()
            return self._target_from_row(
                connection.execute(
                    "SELECT * FROM targets WHERE id = ?", (str(target_id),)
                ).fetchone()
            )

    def _save_sync(
        self,
        target: TargetRecord,
        expected_generation: ConfigurationGeneration | None,
    ) -> TargetConfigurationChange:
        normalized_fqdn = _normalize_fqdn(target.fqdn)
        if target.is_prod != (normalized_fqdn == PRODUCTION_FQDN):
            raise ValueError("production identity is derived from its FQDN")
        if target.posture is TargetPosture.ACTIONS_ENABLED:
            if target.is_prod:
                raise ValueError(
                    "the production appliance is hard-blocked from actions"
                )
            if not self._all_active_packs_trusted_sync():
                raise ValueError(
                    "actions require every active backend pack to be trusted"
                )
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
                    target.posture.value,
                    int(target.is_prod),
                    int(target.verify_ssl),
                    target.auth_source,
                    int(current),
                    str(target.id),
                ),
            )
            connection.commit()
            return TargetConfigurationChange(target.id, previous, current)

    def _authorization_mode_sync(self) -> AuthorizationMode:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute("SELECT value FROM settings WHERE name = 'authorization_mode'")
                .fetchone()
            )
            return AuthorizationMode.LOCAL if row is None else AuthorizationMode(row[0])

    def _set_authorization_mode_sync(self, mode: AuthorizationMode | str) -> int:
        selected = AuthorizationMode(mode)
        with self._write_transaction() as connection:
            current = self._authorization_mode_sync()
            if current is selected:
                return 0
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE api_keys SET revoked = 1, revoked_at = CURRENT_TIMESTAMP"
                " WHERE revoked = 0"
            )
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('authorization_mode', ?)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (selected.value,),
            )
            self._append_configuration_event_sync(
                connection,
                "authorization_mode_changed",
                {
                    "previous_mode": current.value,
                    "current_mode": selected.value,
                    "revoked_key_count": cursor.rowcount,
                },
            )
            connection.commit()
            return cursor.rowcount

    def _append_configuration_event_sync(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        details: Mapping[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO configuration_events(event_type, details_json) VALUES (?, ?)",
            (
                event_type,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )

    def _configuration_events_sync(self, limit: int) -> tuple[dict[str, object], ...]:
        bounded = max(1, min(limit, 500))
        with self._lock:
            rows = (
                self._connection_or_raise()
                .execute(
                    "SELECT event_type, details_json, created_at"
                    " FROM configuration_events ORDER BY id DESC LIMIT ?",
                    (bounded,),
                )
                .fetchall()
            )
            return tuple(
                {
                    "event_type": row["event_type"],
                    "details": json.loads(row["details_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            )

    def _record_configuration_event_sync(
        self, event_type: str, details: Mapping[str, object]
    ) -> None:
        with self._write_transaction() as connection:
            self._append_configuration_event_sync(connection, event_type, details)
            connection.commit()

    def _unsigned_packs_allowed_sync(self) -> bool:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT value FROM settings WHERE name = 'unsigned_packs_allowed'"
                )
                .fetchone()
            )
            return bool(row and row[0] == "1")

    def _set_unsigned_packs_allowed_sync(self, allowed: bool) -> None:
        with self._write_transaction() as connection:
            if allowed and self._has_actions_enabled_target_sync():
                raise ValueError(
                    "unsigned packs cannot be enabled while any target allows actions"
                )
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('unsigned_packs_allowed', ?)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                ("1" if allowed else "0",),
            )
            self._append_configuration_event_sync(
                connection,
                "unsigned_pack_policy_changed",
                {"allowed": allowed},
            )
            connection.commit()

    def _restart_required_sync(self) -> bool:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT value FROM settings WHERE name = 'restart_required'"
                )
                .fetchone()
            )
            return bool(row and row[0] == "1")

    def _set_restart_required_sync(self, required: bool) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "INSERT INTO settings(name, value) VALUES"
                " ('restart_required', ?)"
                " ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                ("1" if required else "0",),
            )
            connection.commit()

    def _has_actions_enabled_target_sync(self) -> bool:
        with self._lock:
            return (
                self._connection_or_raise()
                .execute(
                    "SELECT 1 FROM targets WHERE posture = 'actions_enabled' LIMIT 1"
                )
                .fetchone()
                is not None
            )

    def _all_active_packs_trusted_sync(self) -> bool:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute(
                    "SELECT value FROM settings WHERE name = 'all_active_packs_trusted'"
                )
                .fetchone()
            )
            return bool(row and row[0] == "1")

    def _record_auth_failure_sync(self, target_id: TargetId) -> bool:
        with self._write_transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT auth_failure_count, auth_locked FROM targets WHERE id = ?",
                (str(target_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown target: {target_id}")
            failures = int(row["auth_failure_count"]) + 1
            locked = bool(row["auth_locked"]) or failures >= AUTH_FAILURE_LIMIT
            connection.execute(
                "UPDATE targets SET auth_failure_count = ?, auth_locked = ?"
                " WHERE id = ?",
                (failures, int(locked), str(target_id)),
            )
            if locked and not bool(row["auth_locked"]):
                self._append_configuration_event_sync(
                    connection,
                    "backend_auth_locked",
                    {"target_id": str(target_id), "failure_count": failures},
                )
            connection.commit()
            return locked

    def _record_auth_success_sync(self, target_id: TargetId) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "UPDATE targets SET auth_failure_count = 0"
                " WHERE id = ? AND auth_locked = 0 AND auth_failure_count <> 0",
                (str(target_id),),
            )
            connection.commit()

    def _clear_auth_lockout_sync(self, target_id: TargetId) -> bool:
        with self._write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE targets SET auth_failure_count = 0, auth_locked = 0"
                " WHERE id = ? AND (auth_locked = 1 OR auth_failure_count <> 0)",
                (str(target_id),),
            )
            if cursor.rowcount:
                self._append_configuration_event_sync(
                    connection,
                    "backend_auth_lock_cleared",
                    {"target_id": str(target_id)},
                )
            connection.commit()
            return cursor.rowcount == 1

    def _rotate_credential_key_sync(
        self, batch_size: int, start_new: bool
    ) -> dict[str, int | str]:
        if batch_size < 1 or batch_size > 500:
            raise ValueError("rotation batch size must be between 1 and 500")
        with self._lock:
            connection = self._connection_or_raise()
            state = connection.execute(
                "SELECT * FROM credential_rotation WHERE singleton = 1"
            ).fetchone()
            if state is None or (state["state"] == "complete" and start_new):
                if self._active_key_id is None:
                    raise RuntimeStoreUnavailable("credential keyring is not loaded")
                old_key_id = self._active_key_id
                new_key_id = secrets.token_hex(8)
                self._keys[new_key_id] = secrets.token_bytes(32)
                self._active_key_id = new_key_id
                self._write_keyring()
                total = connection.execute(
                    "SELECT COUNT(*) FROM targets WHERE unusable_reason IS NULL"
                ).fetchone()[0]
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO credential_rotation("
                    " singleton, old_key_id, new_key_id, last_target_id,"
                    " rotated_targets, total_targets, state)"
                    " VALUES (1, ?, ?, NULL, 0, ?, 'running')"
                    " ON CONFLICT(singleton) DO UPDATE SET"
                    " old_key_id = excluded.old_key_id,"
                    " new_key_id = excluded.new_key_id,"
                    " last_target_id = NULL, rotated_targets = 0,"
                    " total_targets = excluded.total_targets, state = 'running'",
                    (old_key_id, new_key_id, total),
                )
                self._append_configuration_event_sync(
                    connection,
                    "credential_rotation_started",
                    {"new_key_id": new_key_id, "target_count": total},
                )
                connection.commit()
                state = connection.execute(
                    "SELECT * FROM credential_rotation WHERE singleton = 1"
                ).fetchone()
            if state["state"] == "complete":
                return self._rotation_status_from_row(state)

            last_target_id = state["last_target_id"]
            rows = connection.execute(
                "SELECT * FROM targets WHERE unusable_reason IS NULL"
                " AND (? IS NULL OR id > ?) ORDER BY id LIMIT ?",
                (last_target_id, last_target_id, batch_size),
            ).fetchall()
            connection.execute("BEGIN IMMEDIATE")
            rotated = int(state["rotated_targets"])
            for row in rows:
                target_id = TargetId(row["id"])
                updates: dict[str, str] = {}
                for column, purpose in (
                    ("username_envelope", "username"),
                    ("password_envelope", "password"),
                    ("root_ca_envelope", "root_ca"),
                ):
                    envelope = row[column]
                    if envelope is not None:
                        updates[column] = self._encrypt(
                            target_id,
                            purpose,
                            self._decrypt(target_id, purpose, envelope),
                        )
                connection.execute(
                    "UPDATE targets SET username_envelope = ?,"
                    " password_envelope = ?, root_ca_envelope = ? WHERE id = ?",
                    (
                        updates["username_envelope"],
                        updates["password_envelope"],
                        updates.get("root_ca_envelope"),
                        str(target_id),
                    ),
                )
                rotated += 1
                last_target_id = str(target_id)
            remaining = connection.execute(
                "SELECT COUNT(*) FROM targets WHERE unusable_reason IS NULL"
                " AND (? IS NULL OR id > ?)",
                (last_target_id, last_target_id),
            ).fetchone()[0]
            final_state = "complete" if remaining == 0 else "running"
            connection.execute(
                "UPDATE credential_rotation SET last_target_id = ?,"
                " rotated_targets = ?, state = ? WHERE singleton = 1",
                (last_target_id, rotated, final_state),
            )
            if final_state == "complete":
                self._append_configuration_event_sync(
                    connection,
                    "credential_rotation_completed",
                    {"new_key_id": state["new_key_id"], "target_count": rotated},
                )
            connection.commit()
            if final_state == "complete":
                self._retire_unused_keys()
            return self._rotation_status_sync() or {}

    def _rotation_status_sync(self) -> dict[str, int | str] | None:
        with self._lock:
            row = (
                self._connection_or_raise()
                .execute("SELECT * FROM credential_rotation WHERE singleton = 1")
                .fetchone()
            )
            return None if row is None else self._rotation_status_from_row(row)

    @staticmethod
    def _rotation_status_from_row(row: sqlite3.Row) -> dict[str, int | str]:
        return {
            "state": row["state"],
            "new_key_id": row["new_key_id"],
            "rotated_targets": int(row["rotated_targets"]),
            "total_targets": int(row["total_targets"]),
        }

    def _retire_keys_after_completed_rotation(self) -> None:
        connection = self._connection_or_raise()
        row = connection.execute(
            "SELECT state FROM credential_rotation WHERE singleton = 1"
        ).fetchone()
        if row is not None and row["state"] == "complete":
            self._retire_unused_keys()

    def _retire_unused_keys(self) -> None:
        connection = self._connection_or_raise()
        referenced: set[str] = set()
        for row in connection.execute(
            "SELECT username_envelope, password_envelope, root_ca_envelope FROM targets"
        ).fetchall():
            for envelope in row:
                if envelope is not None:
                    referenced.add(str(json.loads(envelope)["key_id"]))
        if self._active_key_id is not None:
            referenced.add(self._active_key_id)
        if referenced != set(self._keys):
            self._keys = {
                key_id: value
                for key_id, value in self._keys.items()
                if key_id in referenced
            }
            self._write_keyring()

    def _backup_database_sync(self, destination: Path) -> Path:
        output = Path(destination).resolve()
        keyring = self.keyring_path.resolve()
        if output == keyring or output.is_relative_to(keyring.parent):
            raise ValueError("database backups cannot be written to the keyring volume")
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(output)
            try:
                self._connection_or_raise().backup(target)
                target.commit()
            finally:
                target.close()
        os.chmod(output, 0o600)
        return output

    def _create_api_key_sync(
        self,
        label: str,
        scopes: frozenset[CapabilityName],
        allowed_targets: frozenset[TargetId],
        allowed_endpoints: frozenset[str] | None,
    ) -> str:
        if not label.strip():
            raise ValueError("API key label is required")
        if not scopes.issubset(self._grantable_scopes):
            raise ValueError("API key scopes must be implemented capabilities")
        with self._write_transaction() as connection:
            mode = self._authorization_mode_sync()
            known_endpoints = frozenset({*(kind.value for kind in BackendKind), "vcf"})
            endpoints = frozenset(allowed_endpoints or ())
            selected_targets = frozenset(allowed_targets)
            if mode is AuthorizationMode.GATEWAY:
                if len(endpoints) != 1:
                    raise ValueError("gateway keys must name exactly one endpoint")
                endpoint = next(iter(endpoints))
                existing = connection.execute(
                    "SELECT allowed_endpoints_json FROM api_keys"
                    " WHERE revoked = 0 AND authorization_mode = 'gateway'"
                ).fetchall()
                if any(json.loads(row[0]) == [endpoint] for row in existing):
                    raise ValueError(
                        "gateway mode permits one active key per endpoint registration"
                    )
                target_rows = connection.execute(
                    "SELECT id FROM targets WHERE unusable_reason IS NULL"
                    + ("" if endpoint == "vcf" else " AND backend = ?"),
                    () if endpoint == "vcf" else (endpoint,),
                ).fetchall()
                selected_targets = frozenset(TargetId(row[0]) for row in target_rows)
                scopes = self._grantable_scopes
            elif not selected_targets:
                selected_backends = sorted(
                    endpoints & frozenset(kind.value for kind in BackendKind)
                )
                if endpoints and selected_backends:
                    backend_marks = ",".join("?" for _ in selected_backends)
                    default_rows = connection.execute(
                        "SELECT id FROM targets WHERE unusable_reason IS NULL"
                        f" AND backend IN ({backend_marks})",
                        tuple(selected_backends),
                    ).fetchall()
                elif endpoints:
                    default_rows = []
                else:
                    default_rows = connection.execute(
                        "SELECT id FROM targets WHERE unusable_reason IS NULL"
                    ).fetchall()
                selected_targets = frozenset(TargetId(row[0]) for row in default_rows)
            if not selected_targets:
                raise ValueError("at least one usable target must be allowed")
            placeholders = ",".join("?" for _ in selected_targets)
            found = connection.execute(
                f"SELECT id, backend FROM targets WHERE id IN ({placeholders})"
                " AND unusable_reason IS NULL",
                tuple(str(value) for value in selected_targets),
            ).fetchall()
            if {row["id"] for row in found} != {
                str(value) for value in selected_targets
            }:
                raise ValueError("API key names an unknown or unusable target")
            target_endpoints = frozenset(row["backend"] for row in found)
            if mode is AuthorizationMode.LOCAL and not endpoints:
                endpoints = target_endpoints | {"vcf"}
            if not endpoints or not endpoints.issubset(known_endpoints):
                raise ValueError("API key endpoints must be registered backends")
            if not (
                mode is AuthorizationMode.GATEWAY and endpoints == {"vcf"}
            ) and not target_endpoints.issubset(endpoints):
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
                    , allowed_endpoints_json, authorization_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(key_id),
                    digest,
                    label.strip(),
                    json.dumps(sorted(str(value) for value in scopes)),
                    json.dumps(sorted(str(value) for value in selected_targets)),
                    json.dumps(sorted(endpoints)),
                    mode.value,
                ),
            )
            self._append_configuration_event_sync(
                connection,
                "api_key_created",
                {
                    "key_id": str(key_id),
                    "mode": mode.value,
                    "endpoints": sorted(endpoints),
                },
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
            if cursor.rowcount:
                self._append_configuration_event_sync(
                    connection,
                    "api_key_revoked",
                    {"key_id": str(key_id)},
                )
            connection.commit()
            return cursor.rowcount == 1

    def _list_api_keys_sync(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            rows = (
                self._connection_or_raise()
                .execute(
                    "SELECT key_id, label, scopes_json, allowed_targets_json,"
                    " allowed_endpoints_json, authorization_mode, revoked,"
                    " created_at, revoked_at"
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
                    "authorization_mode": row["authorization_mode"],
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
                    " allowed_endpoints_json, authorization_mode, label, revoked"
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
                authorization_mode=AuthorizationMode(row["authorization_mode"]),
                owner=row["label"],
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
            is_usable=row["unusable_reason"] is None,
            unusable_reason=row["unusable_reason"],
            auth_failure_count=int(row["auth_failure_count"]),
            auth_locked=bool(row["auth_locked"]),
            last_verified_at=(
                None
                if row["last_verified_at"] is None
                else datetime.fromisoformat(row["last_verified_at"])
            ),
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
                "version": ENVELOPE_SCHEMA_VERSION,
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
            version = int(document["version"])
            if version not in (1, ENVELOPE_SCHEMA_VERSION) or key_id not in self._keys:
                raise ValueError
            nonce = base64.urlsafe_b64decode(document["nonce"])
            ciphertext = base64.urlsafe_b64decode(document["ciphertext"])
            plaintext = AESGCM(self._keys[key_id]).decrypt(
                nonce,
                ciphertext,
                self._aad(target_id, purpose, key_id, version=version),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, KeyError, ValueError, UnicodeDecodeError) as exc:
            raise RuntimeStoreUnavailable(
                f"credential envelope failed integrity for target {target_id}"
            ) from exc

    @staticmethod
    def _aad(
        target_id: TargetId,
        purpose: str,
        key_id: str,
        *,
        version: int = ENVELOPE_SCHEMA_VERSION,
    ) -> bytes:
        if version == 1:
            return (
                f"schema=1|target={target_id}|purpose={purpose}|key={key_id}"
            ).encode("utf-8")
        fields = (str(version), str(target_id), purpose, key_id)
        encoded = bytearray()
        for field in fields:
            value = field.encode("utf-8")
            encoded.extend(len(value).to_bytes(4, "big"))
            encoded.extend(value)
        return bytes(encoded)


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
        blocks: list[str] = []
        cursor = 0
        for match in _PEM_BLOCK.finditer(normalized):
            if normalized[cursor : match.start()].strip():
                raise ValueError
            block_type = match.group(1)
            if block_type != "CERTIFICATE":
                raise ValueError(
                    f"root CA bundle contains non-certificate PEM block: {block_type}"
                )
            blocks.append(match.group(0))
            cursor = match.end()
        if normalized[cursor:].strip() or not blocks:
            raise ValueError
        certificates = [
            x509.load_pem_x509_certificate(block.encode("utf-8"))
            for block in blocks
        ]
        if not certificates:
            raise ValueError
        for certificate in certificates:
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
            if not constraints.ca:
                raise ValueError
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=normalized)
    except ValueError as exc:
        if str(exc).startswith("root CA bundle contains non-certificate PEM block:"):
            raise
        raise ValueError(
            "root CA bundle must contain valid PEM CA certificates"
        ) from exc
    except (ssl.SSLError, x509.ExtensionNotFound) as exc:
        raise ValueError(
            "root CA bundle must contain valid PEM CA certificates"
        ) from exc
    return normalized + "\n"


def _certificate_fingerprints(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    certificates = x509.load_pem_x509_certificates(value.encode("utf-8"))
    return tuple(
        certificate.fingerprint(hashes.SHA256()).hex(":")
        for certificate in certificates
    )
