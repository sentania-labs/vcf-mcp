from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from vcf_mcp.backend_packs import DEFAULT_PACKS_PATH, load_backend_packs
from vcf_mcp.contracts import BackendKind, Capability, TargetPosture
from vcf_mcp.pack_trust import (
    OCI_MANIFEST_MEDIA_TYPE,
    PACK_ARTIFACT_TYPE,
    PACK_CERTIFICATE_IDENTITY,
    PACK_CERTIFICATE_ISSUER,
    PACK_LAYER_MEDIA_TYPE,
    PACK_REGISTRY_REFERENCE,
    PackTrustError,
    PackTrustManager,
    _sha256_digest,
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


def _write_oci_layout(layout: Path, pack_bytes: bytes) -> str:
    pack_digest = _sha256_digest(pack_bytes)
    manifest_bytes = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": OCI_MANIFEST_MEDIA_TYPE,
            "artifactType": PACK_ARTIFACT_TYPE,
            "config": {
                "mediaType": "application/vnd.oci.empty.v1+json",
                "digest": "sha256:" + "0" * 64,
                "size": 2,
            },
            "layers": [
                {
                    "mediaType": PACK_LAYER_MEDIA_TYPE,
                    "digest": pack_digest,
                    "size": len(pack_bytes),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    manifest_digest = _sha256_digest(manifest_bytes)
    blobs = layout / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    (layout / "oci-layout").write_text(
        '{"imageLayoutVersion":"1.0.0"}\n'
    )
    (layout / "index.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "manifests": [
                    {
                        "mediaType": OCI_MANIFEST_MEDIA_TYPE,
                        "artifactType": PACK_ARTIFACT_TYPE,
                        "digest": manifest_digest,
                        "size": len(manifest_bytes),
                    }
                ],
            },
            separators=(",", ":"),
        )
    )
    (blobs / pack_digest.removeprefix("sha256:")).write_bytes(pack_bytes)
    (blobs / manifest_digest.removeprefix("sha256:")).write_bytes(manifest_bytes)
    return manifest_digest


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


@pytest.mark.asyncio
async def test_registry_catalog_discovers_versions_and_validates_manifest_bytes(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, _ = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    pack_bytes = (DEFAULT_PACKS_PATH / "ops-networks.json").read_bytes()
    pack = manager._load_bytes(pack_bytes)
    manifest_bytes = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": OCI_MANIFEST_MEDIA_TYPE,
            "artifactType": PACK_ARTIFACT_TYPE,
            "layers": [
                {
                    "mediaType": PACK_LAYER_MEDIA_TYPE,
                    "digest": _sha256_digest(pack_bytes),
                    "size": len(pack_bytes),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    manifest_digest = _sha256_digest(manifest_bytes)
    tag = f"pack-{pack.backend.value}-{pack.version}"

    class FixtureClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", url)
            if url.startswith("https://ghcr.io/token"):
                return httpx.Response(200, json={"token": "anonymous"}, request=request)
            if url.endswith("/tags/list"):
                return httpx.Response(
                    200,
                    json={"tags": [tag, "pack-proof-ignored", "v0.2.0"]},
                    request=request,
                )
            if "/manifests/" in url:
                return httpx.Response(
                    200,
                    content=manifest_bytes,
                    headers={"Docker-Content-Digest": manifest_digest},
                    request=request,
                )
            return httpx.Response(200, content=pack_bytes, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FixtureClient)

    entries = await manager.registry_catalog()

    assert len(entries) == 1
    assert entries[0]["id"] == f"{pack.backend.value}:{pack.version}"
    assert entries[0]["manifest_digest"] == manifest_digest
    assert entries[0]["tool_count"] == len(pack.tools)


@pytest.mark.asyncio
async def test_registry_pack_keeps_offline_startup_verification_and_rollback(
    repository: RuntimeRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cosign, arguments_path = _fake_cosign(tmp_path, monkeypatch)
    manager = _manager(repository, tmp_path, cosign)
    original = json.loads((DEFAULT_PACKS_PATH / "ops.json").read_text())
    first = {**original, "version": "registry-1"}
    second = {**original, "version": "registry-2"}

    async def install(document: dict[str, object]):
        pack_bytes = json.dumps(document).encode()
        fixture = tmp_path / f"fixture-{document['version']}"
        manifest_digest = _write_oci_layout(fixture, pack_bytes)
        pack = manager._load_bytes(pack_bytes)

        async def catalog():
            return (
                {
                    "id": f"{pack.backend.value}:{pack.version}",
                    "backend": pack.backend.value,
                    "version": pack.version,
                    "reference": (
                        f"{PACK_REGISTRY_REFERENCE}:"
                        f"pack-{pack.backend.value}-{pack.version}"
                    ),
                    "manifest_digest": manifest_digest,
                },
            )

        def save(_reference: str, destination: Path) -> None:
            _write_oci_layout(destination, pack_bytes)

        monkeypatch.setattr(manager, "registry_catalog", catalog)
        monkeypatch.setattr(manager, "_save_oci_reference", save)
        staged = await manager.install_from_registry(
            f"{pack.backend.value}:{pack.version}"
        )
        await manager.install_staged(staged.backend, staged.digest)
        return staged

    staged_first = await install(first)
    staged_second = await install(second)

    assert manager.active_path.joinpath("ops.oci.tar").is_file()
    assert not manager.active_path.joinpath("ops.sigstore.json").exists()
    assert await repository.restart_required() is True
    assert manager.verify_active_at_startup()[BackendKind.OPS] == staged_second.digest
    arguments = arguments_path.read_text().splitlines()
    assert arguments[0] == "verify"
    assert "--local-image" in arguments
    assert arguments[arguments.index("--certificate-identity") + 1] == (
        PACK_CERTIFICATE_IDENTITY
    )

    rolled_back = await manager.rollback(BackendKind.OPS, "registry-1")
    assert rolled_back.digest == staged_first.digest
    assert manager.verify_active_at_startup()[BackendKind.OPS] == staged_first.digest

    manager.active_path.joinpath("ops.json").write_bytes(
        manager.active_path.joinpath("ops.json").read_bytes() + b"\n"
    )
    with pytest.raises(PackTrustError, match="does not match"):
        manager.verify_active_at_startup()
