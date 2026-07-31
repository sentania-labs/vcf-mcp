from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from vcf_ops_mcp.contracts import (
    Capability,
    KeyId,
    TargetPosture,
)
from vcf_ops_mcp.runtime_repository import (
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


@pytest.fixture
def repository(tmp_path: Path):
    repo = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=SCOPES,
        bootstrap_password_path=tmp_path
        / "keys"
        / "admin_bootstrap_password",
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
    await repository.save(
        renamed, expected_generation=target.configuration_generation
    )
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
    assert await repository.verify_admin_password(
        "synthetic-bootstrap-password"
    )
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
    assert await repository.verify_admin_password(
        "synthetic-bootstrap-password"
    )

    assert await repository.initialize_admin_from_bootstrap_file() is False
    assert not path.exists()


@pytest.mark.asyncio
async def test_unsafe_bootstrap_password_file_is_refused(
    repository: RuntimeRepository,
) -> None:
    path = repository.bootstrap_password_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic-bootstrap-password")
    path.chmod(0o644)

    assert await repository.initialize_admin_from_bootstrap_file() is False
    assert await repository.has_admin() is False


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
            "UPDATE targets SET password_envelope = username_envelope"
            " WHERE id = ?",
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
