from __future__ import annotations

import dataclasses
import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from vcf_mcp.contracts import (
    AuthorizationMode,
    BackendKind,
    Capability,
    ConfigurationGeneration,
    KeyId,
    TargetPosture,
)
from vcf_mcp.runtime_repository import (
    AllTargetsIntegrityFailed,
    PRODUCTION_FQDN,
    RuntimeRepository,
    RuntimeStoreUnavailable,
)

SCOPES = frozenset(
    {
        Capability.READ_INVENTORY,
        Capability.READ_TARGETS,
        Capability.READ_SKILLS,
    }
)


def synthetic_ca_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture root")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


@pytest.fixture
def repository(tmp_path: Path):
    repo = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=SCOPES,
        bootstrap_password_path=tmp_path / "keys" / "admin_bootstrap_password",
    )
    repo.bootstrap()
    yield repo
    repo.close()


@pytest.mark.asyncio
async def test_target_credentials_are_encrypted_and_survive_restart(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    raw_database = repository.database_path.read_bytes()
    assert b"synthetic-reader" not in raw_database
    assert b"synthetic-password" not in raw_database

    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    reopened = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=SCOPES,
    )
    reopened.bootstrap()
    try:
        stored = await reopened.get(target.id)
        credentials = await reopened.get_credentials(target.id)
    finally:
        reopened.close()
    assert stored == target
    assert credentials.acquire_payload() == {
        "username": "synthetic-reader",
        "password": "synthetic-password",
        "authSource": "LOCAL",
    }
    assert keyring_path.stat().st_mode & 0o777 == 0o600
    assert database_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_v1_runtime_store_migrates_existing_credentials_and_key_scope(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="existing-ops",
        fqdn="existing-ops.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    key = await repository.create_api_key(
        label="existing-key",
        scopes=SCOPES,
        allowed_targets=frozenset({target.id}),
    )
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE targets DROP COLUMN root_ca_envelope")
        connection.execute("ALTER TABLE targets DROP COLUMN backend")
        connection.execute("ALTER TABLE api_keys DROP COLUMN allowed_endpoints_json")
        connection.execute("UPDATE schema_version SET version = 1")
        connection.commit()

    migrated = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=SCOPES,
    )
    migrated.bootstrap()
    try:
        stored = await migrated.get(target.id)
        credentials = await migrated.get_credentials(target.id)
        identity = await migrated.resolve_request_identity(key)
    finally:
        migrated.close()
    assert stored is not None
    assert stored.backend is BackendKind.OPS
    assert credentials.acquire_payload()["password"] == "synthetic-password"
    assert identity is not None
    assert identity.allowed_endpoints == frozenset({"ops", "vcf"})


def test_v1_schema_migration_rolls_back_every_column_on_failure(
    repository: RuntimeRepository,
) -> None:
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE targets DROP COLUMN root_ca_envelope")
        connection.execute("ALTER TABLE targets DROP COLUMN backend")
        connection.execute("UPDATE schema_version SET version = 1")
        connection.commit()

    broken_migration = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=SCOPES,
    )
    with pytest.raises(RuntimeStoreUnavailable):
        broken_migration.bootstrap()

    with sqlite3.connect(database_path) as connection:
        target_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(targets)")
        }
        version = connection.execute("SELECT version FROM schema_version").fetchone()
    assert "backend" not in target_columns
    assert "root_ca_envelope" not in target_columns
    assert version == (1,)


@pytest.mark.asyncio
async def test_v2_runtime_store_migrates_for_remaining_backend_identities(
    repository: RuntimeRepository,
) -> None:
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE schema_version SET version = 2")
        connection.commit()

    migrated = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=SCOPES,
    )
    migrated.bootstrap()
    try:
        target = await migrated.create_target(
            name="fixture-nsx",
            fqdn="nsx.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.NSX,
        )
        stored = await migrated.get(target.id)
    finally:
        migrated.close()

    assert stored is not None
    assert stored.backend is BackendKind.NSX


@pytest.mark.asyncio
async def test_target_edit_rotates_credentials_and_ca_in_one_encrypted_store(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="old-name",
        fqdn="old.example.internal",
        username="synthetic-old-user",
        password="synthetic-old-password",
        auth_source="LOCAL",
        verify_ssl=False,
        backend=BackendKind.VCENTER,
    )
    ca_pem = synthetic_ca_pem()

    updated, change = await repository.update_target(
        target_id=target.id,
        expected_generation=ConfigurationGeneration(1),
        name="new-name",
        fqdn="new.example.internal",
        username="synthetic-new-user",
        password="synthetic-new-password",
        auth_source="LOCAL",
        verify_ssl=True,
        posture=TargetPosture.READ_ONLY,
        root_ca_pem=ca_pem,
    )

    credentials = await repository.get_credentials(target.id)
    stored_ca = await repository.get_root_ca(target.id)
    raw_database = repository.database_path.read_bytes()
    assert updated.name == "new-name"
    assert updated.fqdn == "new.example.internal"
    assert updated.backend is BackendKind.VCENTER
    assert updated.verify_ssl is True
    assert updated.has_custom_ca is True
    assert int(change.previous_generation) == 1
    assert int(change.current_generation) == 2
    assert credentials.acquire_payload()["username"] == "synthetic-new-user"
    assert credentials.acquire_payload()["password"] == "synthetic-new-password"
    assert stored_ca == ca_pem
    for plaintext in (
        b"synthetic-old-user",
        b"synthetic-old-password",
        b"synthetic-new-user",
        b"synthetic-new-password",
        ca_pem.encode("ascii"),
    ):
        assert plaintext not in raw_database


@pytest.mark.asyncio
async def test_targets_default_to_unverified_tls_and_invalid_ca_is_refused(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="default-tls",
        fqdn="default-tls.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
        backend=BackendKind.OPS,
    )
    assert target.verify_ssl is False

    with pytest.raises(ValueError, match="valid PEM"):
        await repository.update_target(
            target_id=target.id,
            expected_generation=target.configuration_generation,
            name=target.name,
            fqdn=target.fqdn,
            username=None,
            password=None,
            auth_source=target.auth_source,
            verify_ssl=True,
            posture=TargetPosture.READ_ONLY,
            root_ca_pem="not a certificate",
        )

    with pytest.raises(ValueError, match="active backend pack"):
        await repository.update_target(
            target_id=target.id,
            expected_generation=target.configuration_generation,
            name=target.name,
            fqdn=target.fqdn,
            username=None,
            password=None,
            auth_source=target.auth_source,
            verify_ssl=False,
            posture=TargetPosture.ACTIONS_ENABLED,
        )


@pytest.mark.asyncio
async def test_endpoint_scopes_must_cover_each_allowed_target(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="vcenter",
        fqdn="vcenter.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
        backend=BackendKind.VCENTER,
    )
    with pytest.raises(ValueError, match="every allowed target"):
        await repository.create_api_key(
            label="wrong endpoint",
            scopes=SCOPES,
            allowed_targets=frozenset({target.id}),
            allowed_endpoints=frozenset({"ops", "vcf"}),
        )

    key = await repository.create_api_key(
        label="vcenter endpoint",
        scopes=SCOPES,
        allowed_targets=frozenset({target.id}),
        allowed_endpoints=frozenset({"vcenter", "vcf"}),
    )
    identity = await repository.resolve_request_identity(key)
    assert identity is not None
    assert identity.allowed_endpoints == frozenset({"vcenter", "vcf"})


@pytest.mark.asyncio
async def test_mode_switch_revokes_every_key_and_gateway_is_one_key_per_endpoint(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="ops",
        fqdn="ops.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    local_one = await repository.create_api_key(
        label="owner-one",
        scopes=frozenset(),
        allowed_targets=frozenset({target.id}),
        allowed_endpoints=frozenset({"ops"}),
    )
    local_two = await repository.create_api_key(
        label="owner-two",
        scopes=frozenset({Capability.READ_INVENTORY}),
        allowed_targets=frozenset({target.id}),
        allowed_endpoints=frozenset({"ops"}),
    )

    revoked = await repository.set_authorization_mode(AuthorizationMode.GATEWAY)

    assert revoked == 2
    assert (await repository.resolve_request_identity(local_one)).revoked is True
    assert (await repository.resolve_request_identity(local_two)).revoked is True
    gateway = await repository.create_api_key(
        label="gateway-ops",
        scopes=frozenset(),
        allowed_targets=frozenset(),
        allowed_endpoints=frozenset({"ops"}),
    )
    identity = await repository.resolve_request_identity(gateway)
    assert identity is not None
    assert identity.authorization_mode is AuthorizationMode.GATEWAY
    assert identity.granted_scopes == SCOPES
    assert identity.allowed_endpoints == {"ops"}
    assert identity.allowed_targets == {target.id}
    with pytest.raises(ValueError, match="one active key per endpoint"):
        await repository.create_api_key(
            label="duplicate-gateway-ops",
            scopes=frozenset(),
            allowed_targets=frozenset(),
            allowed_endpoints=frozenset({"ops"}),
        )
    events = await repository.configuration_events()
    mode_event = next(
        event for event in events if event["event_type"] == "authorization_mode_changed"
    )
    assert mode_event["details"]["revoked_key_count"] == 2


@pytest.mark.asyncio
async def test_auth_failure_lockout_persists_until_operator_clears_it(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="auth-lock",
        fqdn="auth-lock.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    assert await repository.record_auth_failure(target.id) is False
    assert await repository.record_auth_failure(target.id) is False
    assert await repository.record_auth_failure(target.id) is True
    locked = await repository.get(target.id)
    assert locked is not None and locked.auth_locked
    with pytest.raises(RuntimeStoreUnavailable, match="operator reset"):
        await repository.get_credentials(target.id)
    assert await repository.clear_auth_lockout(target.id) is True
    assert (await repository.get(target.id)).auth_locked is False


@pytest.mark.asyncio
async def test_credential_rotation_resumes_after_restart_and_retires_old_key(
    repository: RuntimeRepository,
) -> None:
    targets = []
    for index in range(2):
        targets.append(
            await repository.create_target(
                name=f"rotate-{index}",
                fqdn=f"rotate-{index}.example.internal",
                username=f"synthetic-reader-{index}",
                password=f"synthetic-password-{index}",
                auth_source="LOCAL",
                verify_ssl=False,
            )
        )
    first = await repository.rotate_credential_key(batch_size=1, start_new=True)
    assert first["state"] == "running"
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()

    resumed = RuntimeRepository(database_path, keyring_path, grantable_scopes=SCOPES)
    resumed.bootstrap()
    try:
        final = await resumed.rotate_credential_key(batch_size=1)
        assert final["state"] == "complete"
        for index, target in enumerate(targets):
            credentials = await resumed.get_credentials(target.id)
            assert (
                credentials.acquire_payload()["username"] == f"synthetic-reader-{index}"
            )
        keyring = json.loads(keyring_path.read_text())
        assert list(keyring["keys"]) == [keyring["active_key_id"]]
    finally:
        resumed.close()


@pytest.mark.asyncio
async def test_database_backup_restores_with_separately_held_keyring(
    repository: RuntimeRepository, tmp_path: Path
) -> None:
    target = await repository.create_target(
        name="restore",
        fqdn="restore.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    database_backup = await repository.backup_database(
        tmp_path / "database-backup" / "config.sqlite3"
    )
    separate_keyring = tmp_path / "separate-keyring" / "credential_keyring.json"
    separate_keyring.parent.mkdir()
    shutil.copy2(repository.keyring_path, separate_keyring)

    restored = RuntimeRepository(
        database_backup, separate_keyring, grantable_scopes=SCOPES
    )
    restored.bootstrap()
    try:
        credentials = await restored.get_credentials(target.id)
        assert credentials.acquire_payload()["password"] == "synthetic-password"
    finally:
        restored.close()
    with pytest.raises(ValueError, match="keyring volume"):
        await repository.backup_database(repository.keyring_path.parent / "bad.sqlite3")
    with pytest.raises(ValueError, match="keyring volume"):
        await repository.backup_database(
            repository.keyring_path.parent / "nested" / "bad.sqlite3"
        )


@pytest.mark.asyncio
async def test_startup_quarantines_one_bad_target_and_refuses_when_all_are_bad(
    repository: RuntimeRepository,
) -> None:
    good = await repository.create_target(
        name="good",
        fqdn="good.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    bad = await repository.create_target(
        name="bad",
        fqdn="bad.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE targets SET password_envelope = '{\"broken\":true}' WHERE id = ?",
            (str(bad.id),),
        )
        connection.commit()
    reopened = RuntimeRepository(database_path, keyring_path, grantable_scopes=SCOPES)
    reopened.bootstrap()
    try:
        assert (await reopened.get(good.id)).is_usable is True
        quarantined = await reopened.get(bad.id)
        assert quarantined is not None and quarantined.is_usable is False
        assert {target.id for target in reopened.list_at_startup()} == {good.id}
    finally:
        reopened.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE targets SET password_envelope = '{\"broken\":true}' WHERE id = ?",
            (str(good.id),),
        )
        connection.commit()
    refused = RuntimeRepository(database_path, keyring_path, grantable_scopes=SCOPES)
    with pytest.raises(
        AllTargetsIntegrityFailed,
        match="every configured target failed credential integrity verification",
    ):
        refused.bootstrap()


@pytest.mark.asyncio
async def test_quarantine_requires_corrupt_root_ca_to_be_replaced_or_removed(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="damaged-ca",
        fqdn="damaged-ca.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
        root_ca_pem=synthetic_ca_pem(),
    )
    await repository.create_target(
        name="healthy",
        fqdn="healthy.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE targets SET root_ca_envelope = '{\"broken\":true}' WHERE id = ?",
            (str(target.id),),
        )
        connection.commit()

    reopened = RuntimeRepository(database_path, keyring_path, grantable_scopes=SCOPES)
    reopened.bootstrap()
    try:
        quarantined = await reopened.get(target.id)
        assert quarantined is not None and quarantined.is_usable is False
        with pytest.raises(ValueError, match="root CA must be replaced or removed"):
            await reopened.update_target(
                target_id=target.id,
                expected_generation=target.configuration_generation,
                name=target.name,
                fqdn=target.fqdn,
                username="synthetic-new-reader",
                password="synthetic-new-password",
                auth_source=target.auth_source,
                verify_ssl=False,
                posture=TargetPosture.READ_ONLY,
            )
        still_quarantined = await reopened.get(target.id)
        assert still_quarantined is not None
        assert still_quarantined.is_usable is False
        assert (
            still_quarantined.configuration_generation
            == target.configuration_generation
        )

        recovered, _ = await reopened.update_target(
            target_id=target.id,
            expected_generation=target.configuration_generation,
            name=target.name,
            fqdn=target.fqdn,
            username="synthetic-new-reader",
            password="synthetic-new-password",
            auth_source=target.auth_source,
            verify_ssl=False,
            posture=TargetPosture.READ_ONLY,
            clear_root_ca=True,
        )
        assert recovered.is_usable is True
        assert recovered.has_custom_ca is False
        assert await reopened.get_root_ca(target.id) is None
    finally:
        reopened.close()


def test_aad_is_length_prefixed_and_has_no_delimiter_collision() -> None:
    first = RuntimeRepository._aad(
        "target|purpose=password", "username", "key", version=2
    )
    second = RuntimeRepository._aad(
        "target", "password|purpose=username", "key", version=2
    )
    assert first != second


@pytest.mark.asyncio
async def test_production_fqdn_is_structurally_read_only(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="prod",
        fqdn=PRODUCTION_FQDN.upper(),
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    assert target.is_prod is True
    assert target.posture is TargetPosture.READ_ONLY


@pytest.mark.asyncio
async def test_save_derives_prod_identity_from_the_normalized_fqdn(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    disguised_prod = dataclasses.replace(
        target,
        fqdn=f" {PRODUCTION_FQDN.upper()}. ",
        is_prod=False,
    )
    with pytest.raises(ValueError):
        await repository.save(
            disguised_prod,
            expected_generation=target.configuration_generation,
        )

    renamed = dataclasses.replace(target, fqdn=" Devel2.Example.Internal. ")
    await repository.save(renamed, expected_generation=target.configuration_generation)
    stored = await repository.get(target.id)
    assert stored is not None
    assert stored.fqdn == "devel2.example.internal"
    assert stored.is_prod is False


@pytest.mark.asyncio
async def test_api_keys_are_stored_as_digests_and_revocation_is_immediate(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    key = await repository.create_api_key(
        label="test",
        scopes=SCOPES,
        allowed_targets=frozenset({target.id}),
    )
    assert key.startswith("vok_")
    assert key.encode() not in repository.database_path.read_bytes()
    identity = await repository.resolve_request_identity(key)
    assert identity is not None
    assert identity.revoked is False
    assert identity.allowed_targets == frozenset({target.id})
    assert await repository.resolve_request_identity(key + "wrong") is None

    assert await repository.revoke_api_key(identity.key_id) is True
    revoked = await repository.resolve_request_identity(key)
    assert revoked is not None
    assert revoked.revoked is True
    assert await repository.revoke_api_key(KeyId("missing")) is False


@pytest.mark.asyncio
async def test_bootstrap_password_file_is_consumed_once(
    repository: RuntimeRepository,
) -> None:
    path = repository.bootstrap_password_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic-bootstrap-password")
    path.chmod(0o600)

    assert await repository.initialize_admin_from_bootstrap_file() is True
    assert not path.exists()
    assert await repository.verify_admin_password("synthetic-bootstrap-password")
    assert not await repository.verify_admin_password("wrong")
    assert await repository.initialize_admin_from_bootstrap_file() is False


@pytest.mark.asyncio
async def test_bootstrap_cleanup_retries_after_unlink_failure(
    repository: RuntimeRepository,
) -> None:
    path = repository.bootstrap_password_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic-bootstrap-password")
    path.chmod(0o600)

    with mock.patch.object(
        Path,
        "unlink",
        side_effect=OSError("synthetic unlink failure"),
    ):
        with pytest.raises(RuntimeStoreUnavailable):
            await repository.initialize_admin_from_bootstrap_file()

    assert await repository.has_admin() is True
    assert path.exists()
    assert await repository.verify_admin_password("synthetic-bootstrap-password")

    assert await repository.initialize_admin_from_bootstrap_file() is False
    assert not path.exists()


@pytest.mark.asyncio
async def test_permissive_bootstrap_password_file_is_corrected_and_consumed(
    repository: RuntimeRepository,
) -> None:
    path = repository.bootstrap_password_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic-bootstrap-password")
    path.chmod(0o644)

    assert await repository.initialize_admin_from_bootstrap_file() is True
    assert await repository.has_admin() is True
    assert not path.exists()


@pytest.mark.asyncio
async def test_missing_keyring_never_regenerates_over_ciphertext(
    repository: RuntimeRepository,
) -> None:
    await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    database_path = repository.database_path
    keyring_path = repository.keyring_path
    repository.close()
    keyring_path.unlink()

    reopened = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=SCOPES,
    )
    with pytest.raises(RuntimeStoreUnavailable):
        reopened.bootstrap()


@pytest.mark.asyncio
async def test_ciphertext_cannot_be_moved_between_fields(
    repository: RuntimeRepository,
) -> None:
    target = await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=True,
    )
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE targets SET password_envelope = username_envelope WHERE id = ?",
            (str(target.id),),
        )
        connection.commit()
    with pytest.raises(RuntimeStoreUnavailable):
        await repository.get_credentials(target.id)


@pytest.mark.asyncio
async def test_readiness_recovers_after_transient_write_failure(
    repository: RuntimeRepository,
) -> None:
    assert await repository.is_ready() is True

    def deny_inserts(action, arg1, arg2, db_name, trigger):
        if action == sqlite3.SQLITE_INSERT:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection = repository._connection
    assert connection is not None
    connection.set_authorizer(deny_inserts)
    assert await repository.is_ready() is False
    assert await repository.is_ready() is False

    connection.set_authorizer(None)
    assert await repository.is_ready() is True
