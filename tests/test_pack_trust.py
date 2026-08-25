from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from vcf_mcp.backend_packs import DEFAULT_PACKS_PATH, load_backend_packs
from vcf_mcp.contracts import BackendKind, Capability, TargetPosture
from vcf_mcp.pack_trust import (
    PACK_CERTIFICATE_IDENTITY,
    PACK_CERTIFICATE_ISSUER,
    PackTrustError,
    PackTrustManager,
)
from vcf_mcp.runtime_repository import RuntimeRepository


SCOPES = frozenset({Capability.READ_INVENTORY})


@pytest.fixture
def repository(tmp_path: Path):
    value = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=SCOPES,
    )
    value.bootstrap()
    yield value
    value.close()


def _fake_cosign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int = 0):
    executable = tmp_path / "cosign"
    arguments = tmp_path / "cosign-arguments"
    executable.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$COSIGN_ARGS_FILE"\n'
        'exit "$COSIGN_EXIT_CODE"\n'
    )
    executable.chmod(0o755)
    monkeypatch.setenv("COSIGN_ARGS_FILE", str(arguments))
    monkeypatch.setenv("COSIGN_EXIT_CODE", str(exit_code))
    return executable, arguments


def _manager(
    repository: RuntimeRepository,
    tmp_path: Path,
    cosign: Path,
) -> PackTrustManager:
    trust_root = tmp_path / "trust" / "trusted-root.json"
    trust_root.parent.mkdir()
    trust_root.write_text('{"certificateAuthorities":[{"fixture":true}]}')
    return PackTrustManager(
        repository,
        store_path=tmp_path / "pack-store",
        trust_root_path=trust_root,
        cosign_path=cosign,
        temp_path=tmp_path / "temp",
    )


@pytest.mark.asyncio
async def test_signed_install_pins_exact_workflow_identity_and_github_issuer(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, arguments_path = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    pack_bytes = (DEFAULT_PACKS_PATH / "ops.json").read_bytes()

    result = await manager.install_manual(pack_bytes, b'{"fixture":"bundle"}')
    await manager.install_staged(result.backend, result.digest)

    assert result.signed is True
    assert result.activation == "restart_required"
    arguments = arguments_path.read_text().splitlines()
    assert arguments[0] == "verify-blob"
    assert arguments[arguments.index("--certificate-identity") + 1] == (
        PACK_CERTIFICATE_IDENTITY
    )
    assert arguments[arguments.index("--certificate-oidc-issuer") + 1] == (
        PACK_CERTIFICATE_ISSUER
    )
    assert "--offline" in arguments
    assert "--" in arguments
    decisions = manager.verify_active_at_startup()
    assert decisions[BackendKind.OPS] == result.digest
    packs = load_backend_packs(
        operator_path=manager.active_path,
        verified_operator_digests=decisions,
    )
    assert packs[BackendKind.OPS].unsigned is False


@pytest.mark.asyncio
async def test_signature_mismatch_is_refused_and_audited(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, _ = _fake_cosign(tmp_path, monkeypatch, exit_code=1)
    manager = _manager(repository, tmp_path, cosign)

    with pytest.raises(PackTrustError, match="workflow identity"):
        await manager.install_manual(
            (DEFAULT_PACKS_PATH / "ops.json").read_bytes(),
            b'{"fixture":"bundle"}',
        )

    events = await repository.configuration_events()
    assert events[0]["event_type"] == "pack_signature_refused"


@pytest.mark.asyncio
async def test_refresh_persists_beside_packs_and_overrides_immutable_image_root(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, arguments_path = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    shipped_content = manager.shipped_trust_root_path.read_bytes()
    manager.shipped_trust_root_path.chmod(0o444)
    refreshed_content = b'{"certificateAuthorities":[{"refreshed":true}]}'

    class FixtureClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FixtureClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            return httpx.Response(
                200,
                content=refreshed_content,
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", FixtureClient)

    digest = await manager.refresh_trust_root()

    assert digest == hashlib.sha256(refreshed_content).hexdigest()
    assert manager.shipped_trust_root_path.read_bytes() == shipped_content
    assert manager.persisted_trust_root_path.read_bytes() == refreshed_content
    assert manager.trust_root_path == manager.persisted_trust_root_path

    await manager.install_manual(
        (DEFAULT_PACKS_PATH / "ops.json").read_bytes(),
        b'{"fixture":"bundle"}',
    )
    arguments = arguments_path.read_text().splitlines()
    assert arguments[arguments.index("--trusted-root") + 1] == str(
        manager.persisted_trust_root_path
    )


@pytest.mark.asyncio
async def test_unsigned_install_is_off_by_default_and_refused_with_actions(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, _ = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    pack_bytes = (DEFAULT_PACKS_PATH / "ops.json").read_bytes()
    with pytest.raises(PackTrustError, match="disabled"):
        await manager.install_manual(pack_bytes, None)

    await repository.set_unsigned_packs_allowed(True)
    repository.set_pack_action_trust_at_startup(True)
    target = await repository.create_target(
        name="devel",
        fqdn="devel.example.internal",
        username="synthetic-reader",
        password="synthetic-password",
        auth_source="LOCAL",
        verify_ssl=False,
    )
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
    with pytest.raises(PackTrustError, match="allows actions"):
        await manager.install_manual(pack_bytes, None)


@pytest.mark.asyncio
async def test_previous_pack_version_is_retained_and_rollback_is_one_action(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, _ = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    original = json.loads((DEFAULT_PACKS_PATH / "ops.json").read_text())
    first = dict(original)
    first["version"] = "1.0.0"
    second = dict(original)
    second["version"] = "2.0.0"
    staged_first = await manager.install_manual(json.dumps(first).encode(), b"{}")
    await manager.install_staged(staged_first.backend, staged_first.digest)
    staged_second = await manager.install_manual(json.dumps(second).encode(), b"{}")
    await manager.install_staged(staged_second.backend, staged_second.digest)

    assert {entry["version"] for entry in manager.retained_versions()} == {"1.0.0"}
    result = await manager.rollback(BackendKind.OPS, "1.0.0")
    assert result.version == "1.0.0"
