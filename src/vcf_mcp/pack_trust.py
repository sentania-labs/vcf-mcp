"""Signed backend-pack verification, staging, rollback, and trust refresh."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from vcf_mcp.backend_packs import BackendPack, _load_pack_directory
from vcf_mcp.contracts import BackendKind
from vcf_mcp.runtime_repository import RuntimeRepository


PACK_CERTIFICATE_IDENTITY = (
    "https://github.com/sentania-labs/vcf-mcp/.github/workflows/"
    "release-packs.yml@refs/heads/main"
)
PACK_CERTIFICATE_ISSUER = "https://token.actions.githubusercontent.com"
PACK_REGISTRY = "ghcr.io"
MAX_REGISTRY_TAG_PAGES = 50
MAX_REGISTRY_REDIRECTS = 5
PACK_REGISTRY_REPOSITORY = "sentania-labs/vcf-mcp"
PACK_REGISTRY_REFERENCE = f"{PACK_REGISTRY}/{PACK_REGISTRY_REPOSITORY}"
PACK_REGISTRY_TOKEN_URL = (
    "https://ghcr.io/token?service=ghcr.io&"
    f"scope=repository:{PACK_REGISTRY_REPOSITORY}:pull"
)
PACK_ARTIFACT_TYPE = "application/vnd.sentania.vcf-mcp.backend-pack.v1+json"
PACK_LAYER_MEDIA_TYPE = PACK_ARTIFACT_TYPE
OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
PACK_TAG_PREFIX = "pack-"
TRUST_ROOT_REFRESH_URL = (
    "https://raw.githubusercontent.com/sigstore/root-signing/"
    "main/repository/targets/trusted_root.json"
)
DEFAULT_PACK_STORE = Path("/data/backend-packs")
DEFAULT_TRUST_ROOT = Path("/app/trust/sigstore-trusted-root.json")
PERSISTED_TRUST_ROOT_NAME = "sigstore-trusted-root.json"
DEFAULT_COSIGN = Path("/usr/local/bin/cosign")
MAX_PACK_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_OCI_LAYOUT_BYTES = 8 * 1024 * 1024
MAX_TRUST_ROOT_BYTES = 1024 * 1024


class PackTrustError(RuntimeError):
    """A pack was refused without exposing verifier output."""


@dataclass(frozen=True, slots=True)
class RegistryCatalog:
    entries: tuple[dict[str, object], ...]
    skipped: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class PackInstallResult:
    backend: str
    version: str
    digest: str
    tool_count: int
    estimated_definition_tokens: int
    signed: bool
    activation: str = "restart_required"


class PackTrustManager:
    """Own the only path from uploaded bytes to startup-visible pack files."""

    def __init__(
        self,
        repository: RuntimeRepository,
        *,
        store_path: Path = DEFAULT_PACK_STORE,
        trust_root_path: Path = DEFAULT_TRUST_ROOT,
        persisted_trust_root_path: Path | None = None,
        cosign_path: Path = DEFAULT_COSIGN,
        temp_path: Path = Path("/tmp"),
        certificate_identity: str = PACK_CERTIFICATE_IDENTITY,
        certificate_issuer: str = PACK_CERTIFICATE_ISSUER,
    ) -> None:
        self._repository = repository
        self.store_path = Path(store_path)
        self.active_path = self.store_path / "active"
        self.staged_path = self.store_path / "staged"
        self.retained_path = self.store_path / "retained"
        self.shipped_trust_root_path = Path(trust_root_path)
        self.persisted_trust_root_path = (
            Path(persisted_trust_root_path)
            if persisted_trust_root_path is not None
            else self.store_path / "trust" / PERSISTED_TRUST_ROOT_NAME
        )
        self.cosign_path = Path(cosign_path)
        self.temp_path = Path(temp_path)
        self.certificate_identity = certificate_identity
        self.certificate_issuer = certificate_issuer

    @property
    def trust_root_path(self) -> Path:
        """Return the operator-refreshed root when present, else the image root."""

        if self.persisted_trust_root_path.is_file():
            return self.persisted_trust_root_path
        return self.shipped_trust_root_path

    def verify_active_at_startup(self) -> dict[BackendKind, str | None]:
        """Re-verify every active pack before the registry can see it."""

        decisions: dict[BackendKind, str | None] = {}
        if not self.active_path.exists():
            return decisions
        for pack_path in sorted(self.active_path.glob("*.json")):
            if pack_path.name.endswith(".sigstore.json"):
                continue
            bundle_path = pack_path.with_suffix(".sigstore.json")
            oci_archive_path = pack_path.with_suffix(".oci.tar")
            pack_bytes = pack_path.read_bytes()
            digest = hashlib.sha256(pack_bytes).hexdigest()
            try:
                if bundle_path.exists() and oci_archive_path.exists():
                    raise PackTrustError(
                        "active pack has conflicting signature material"
                    )
                if oci_archive_path.exists():
                    if self._verify_oci_archive(oci_archive_path) != pack_bytes:
                        raise PackTrustError(
                            "active pack does not match its signed OCI artifact"
                        )
                    verified_digest: str | None = digest
                elif bundle_path.exists():
                    self._verify_signature(pack_path, bundle_path)
                    verified_digest: str | None = digest
                else:
                    self._refuse_unsigned_if_unsafe()
                    verified_digest = None
                pack = self._load_one(pack_path)
                decisions[pack.backend] = verified_digest
            except Exception:
                self._repository.record_configuration_event_at_startup(
                    "pack_signature_refused",
                    {"backend": pack_path.stem, "digest": digest},
                )
                raise
        return decisions

    async def install_manual(
        self, pack_bytes: bytes, bundle_bytes: bytes | None
    ) -> PackInstallResult:
        return await asyncio.to_thread(
            self._install_manual_sync, pack_bytes, bundle_bytes
        )

    async def rollback(
        self, backend: BackendKind | str, version: str
    ) -> PackInstallResult:
        return await asyncio.to_thread(
            self._rollback_sync, BackendKind(backend), version
        )

    async def install_staged(
        self, backend: BackendKind | str, digest: str
    ) -> PackInstallResult:
        return await asyncio.to_thread(
            self._install_staged_sync, BackendKind(backend), digest
        )

    async def refresh_trust_root(self) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(TRUST_ROOT_REFRESH_URL)
            response.raise_for_status()
            content = response.content
        if len(content) > MAX_TRUST_ROOT_BYTES:
            raise PackTrustError("refreshed trust root exceeds the size limit")
        _validate_trust_root(content)
        try:
            await asyncio.to_thread(
                _atomic_private_write, self.persisted_trust_root_path, content
            )
        except OSError as exc:
            raise PackTrustError("refreshed trust root could not be persisted") from exc
        digest = hashlib.sha256(content).hexdigest()
        await self._repository.record_configuration_event(
            "pack_trust_root_refreshed", {"digest": digest}
        )
        return digest

    async def registry_catalog(self) -> RegistryCatalog:
        """Discover the newest signed pack version per backend from GHCR."""

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = await _registry_pull_headers(client)
            tags: list[str] = []
            page_url = str(
                httpx.URL(
                    f"https://{PACK_REGISTRY}/v2/{PACK_REGISTRY_REPOSITORY}"
                    "/tags/list",
                    params={"n": "1000"},
                )
            )
            for _ in range(MAX_REGISTRY_TAG_PAGES):
                tags_headers, tags_bytes, _ = await _read_registry_bytes(
                    client,
                    page_url,
                    headers=headers,
                    max_bytes=MAX_BUNDLE_BYTES,
                    description="registry tag response",
                )
                try:
                    page_tags = json.loads(tags_bytes).get("tags", [])
                    if not isinstance(page_tags, list):
                        raise TypeError
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise PackTrustError(
                        "registry tag response is malformed"
                    ) from exc
                tags.extend(str(value) for value in page_tags)
                next_link = httpx.Response(200, headers=tags_headers).links.get(
                    "next", {}
                ).get("url")
                if not next_link:
                    break
                page_url = str(httpx.URL(page_url).join(next_link))
            else:
                raise PackTrustError(
                    "registry tag listing exceeded the pagination limit"
                )

            skipped: list[dict[str, str]] = []
            newest: dict[BackendKind, tuple[tuple[object, ...], str, str]] = {}
            for tag in sorted({str(value) for value in tags}):
                parsed = _pack_tag_parts(tag)
                if parsed is None:
                    continue
                backend, version = parsed
                try:
                    _safe_version(version)
                except PackTrustError as exc:
                    skipped.append(
                        {"tag": tag, "backend": backend.value, "reason": str(exc)}
                    )
                    continue
                key = _version_sort_key(version)
                if backend not in newest or key > newest[backend][0]:
                    newest[backend] = (key, version, tag)

            entries: list[dict[str, object]] = []
            for backend in sorted(newest, key=lambda value: value.value):
                _, version, tag = newest[backend]
                try:
                    entries.append(
                        await self._registry_entry(
                            client,
                            headers=headers,
                            tag=tag,
                            backend=backend,
                            version=version,
                        )
                    )
                except PackTrustError as exc:
                    skipped.append(
                        {"tag": tag, "backend": backend.value, "reason": str(exc)}
                    )
                except httpx.HTTPError as exc:
                    skipped.append(
                        {
                            "tag": tag,
                            "backend": backend.value,
                            "reason": f"registry request failed: {exc}",
                        }
                    )
        return RegistryCatalog(entries=tuple(entries), skipped=tuple(skipped))

    async def install_from_registry(self, entry_id: str) -> PackInstallResult:
        backend_value, separator, version = entry_id.partition(":")
        if not separator or not version.strip():
            raise PackTrustError("registry pack selection must name a version")
        try:
            backend = BackendKind(backend_value.strip())
        except ValueError as exc:
            raise PackTrustError(
                "registry pack selection names an unknown backend"
            ) from exc
        version = _safe_version(version.strip())
        entry = await self._registry_entry_for_tag(backend, version)
        return await asyncio.to_thread(
            self._install_from_registry_sync,
            str(entry["reference"]),
            str(entry["manifest_digest"]),
            backend,
            version,
        )

    async def _registry_entry_for_tag(
        self, backend: BackendKind, version: str
    ) -> dict[str, object]:
        tag = f"{PACK_TAG_PREFIX}{backend.value}-{version}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = await _registry_pull_headers(client)
            return await self._registry_entry(
                client,
                headers=headers,
                tag=tag,
                backend=backend,
                version=version,
            )

    async def _registry_entry(
        self,
        client: httpx.AsyncClient,
        *,
        headers: dict[str, str],
        tag: str,
        backend: BackendKind,
        version: str,
    ) -> dict[str, object]:
        manifest_url = (
            f"https://{PACK_REGISTRY}/v2/{PACK_REGISTRY_REPOSITORY}/"
            f"manifests/{quote(tag, safe='')}"
        )
        manifest_headers, manifest_bytes, _ = await _read_registry_bytes(
            client,
            manifest_url,
            headers={**headers, "Accept": OCI_MANIFEST_MEDIA_TYPE},
            max_bytes=MAX_BUNDLE_BYTES,
            description="registry pack manifest",
        )
        manifest_digest = _sha256_digest(manifest_bytes)
        advertised_digest = manifest_headers.get("Docker-Content-Digest")
        if advertised_digest and advertised_digest != manifest_digest:
            raise PackTrustError("registry pack manifest digest does not match")
        layer = _pack_layer_from_manifest(manifest_bytes)
        if int(layer["size"]) > MAX_PACK_BYTES:
            raise PackTrustError("registry pack exceeds the size limit")
        blob_digest = str(layer["digest"])
        _, pack_bytes, blob_redirects = await _read_registry_bytes(
            client,
            f"https://{PACK_REGISTRY}/v2/{PACK_REGISTRY_REPOSITORY}/"
            f"blobs/{quote(blob_digest, safe=':')}",
            headers=headers,
            max_bytes=MAX_PACK_BYTES,
            description="registry pack",
        )
        _verify_blob_descriptor(pack_bytes, layer, limit=MAX_PACK_BYTES)
        await asyncio.to_thread(
            self._verify_registry_reference,
            f"{PACK_REGISTRY_REFERENCE}:{tag}@{manifest_digest}",
        )
        pack = self._load_bytes(pack_bytes)
        if pack.backend != backend or pack.version != version:
            raise PackTrustError("registry tag does not match the pack identity")
        result = _install_result(pack, signed=True)
        return {
            "id": f"{backend.value}:{version}",
            "backend": backend.value,
            "version": version,
            "tool_count": result.tool_count,
            "estimated_definition_tokens": result.estimated_definition_tokens,
            "reference": f"{PACK_REGISTRY_REFERENCE}:{tag}",
            "manifest_digest": manifest_digest,
            "blob_redirects": blob_redirects,
        }

    def retained_versions(self) -> tuple[dict[str, str], ...]:
        if not self.retained_path.exists():
            return ()
        versions: list[dict[str, str]] = []
        for path in sorted(self.retained_path.glob("*/*.json")):
            if path.name.endswith(".sigstore.json"):
                continue
            pack = self._load_one(path)
            versions.append({"backend": pack.backend.value, "version": pack.version})
        return tuple(versions)

    def _install_from_registry_sync(
        self,
        reference: str,
        manifest_digest: str,
        backend: BackendKind,
        version: str,
    ) -> PackInstallResult:
        if not reference.startswith(f"{PACK_REGISTRY_REFERENCE}:"):
            raise PackTrustError("registry pack reference is outside the pinned repository")
        _validated_sha256_digest(manifest_digest)
        self.temp_path.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=self.temp_path) as temporary:
                layout_path = Path(temporary) / "signed-pack"
                self._save_oci_reference(
                    f"{reference}@{manifest_digest}",
                    layout_path,
                )
                pack_bytes = self._verify_oci_layout(
                    layout_path,
                    expected_manifest_digest=manifest_digest,
                )
                pack = self._load_bytes(pack_bytes)
                if pack.backend != backend or pack.version != version:
                    raise PackTrustError(
                        "verified OCI artifact does not match the selected pack"
                    )
                return self._stage_candidate(
                    pack_bytes,
                    pack=pack,
                    signed=True,
                    oci_archive_bytes=_archive_oci_layout(layout_path),
                )
        except Exception:
            self._repository.record_configuration_event_at_startup(
                "pack_signature_refused",
                {
                    "backend": backend.value,
                    "manifest_digest": manifest_digest,
                },
            )
            raise

    def _install_manual_sync(
        self, pack_bytes: bytes, bundle_bytes: bytes | None
    ) -> PackInstallResult:
        if not pack_bytes or len(pack_bytes) > MAX_PACK_BYTES:
            raise PackTrustError("pack file is empty or exceeds the size limit")
        if bundle_bytes is not None and len(bundle_bytes) > MAX_BUNDLE_BYTES:
            raise PackTrustError("signature bundle exceeds the size limit")
        self.temp_path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.temp_path) as temporary:
            temporary_path = Path(temporary)
            pack_path = temporary_path / "candidate.json"
            bundle_path = temporary_path / "candidate.sigstore.json"
            pack_path.write_bytes(pack_bytes)
            os.chmod(pack_path, 0o600)
            signed = bundle_bytes is not None
            try:
                if signed:
                    bundle_path.write_bytes(bundle_bytes or b"")
                    os.chmod(bundle_path, 0o600)
                    self._verify_signature(pack_path, bundle_path)
                else:
                    self._refuse_unsigned_if_unsafe()
                pack = self._load_one(pack_path)
            except Exception:
                digest = hashlib.sha256(pack_bytes).hexdigest()
                self._repository.record_configuration_event_at_startup(
                    "pack_signature_refused", {"digest": digest}
                )
                raise
            return self._stage_candidate(
                pack_bytes,
                pack=pack,
                signed=signed,
                bundle_bytes=bundle_bytes,
            )

    def _stage_candidate(
        self,
        pack_bytes: bytes,
        *,
        pack: BackendPack,
        signed: bool,
        bundle_bytes: bytes | None = None,
        oci_archive_bytes: bytes | None = None,
    ) -> PackInstallResult:
        self.staged_path.mkdir(parents=True, exist_ok=True)
        destination = self.staged_path / f"{pack.backend.value}.json"
        _atomic_private_write(destination, pack_bytes)
        destination_bundle = destination.with_suffix(".sigstore.json")
        destination_oci = destination.with_suffix(".oci.tar")
        if bundle_bytes is not None:
            _atomic_private_write(destination_bundle, bundle_bytes)
            destination_oci.unlink(missing_ok=True)
        elif oci_archive_bytes is not None:
            _atomic_private_write(destination_oci, oci_archive_bytes)
            destination_bundle.unlink(missing_ok=True)
        else:
            destination_bundle.unlink(missing_ok=True)
            destination_oci.unlink(missing_ok=True)
        self._repository.record_configuration_event_at_startup(
            "pack_staged",
            {
                "backend": pack.backend.value,
                "version": pack.version,
                "digest": pack.digest,
                "signed": signed,
            },
        )
        return _install_result(pack, signed=signed)

    def _install_staged_sync(
        self, backend: BackendKind, digest: str
    ) -> PackInstallResult:
        candidate = self.staged_path / f"{backend.value}.json"
        if not candidate.exists():
            raise PackTrustError("staged pack does not exist")
        candidate_bytes = candidate.read_bytes()
        if hashlib.sha256(candidate_bytes).hexdigest() != digest:
            raise PackTrustError("staged pack changed after operator review")
        bundle = candidate.with_suffix(".sigstore.json")
        oci_archive = candidate.with_suffix(".oci.tar")
        if bundle.exists() and oci_archive.exists():
            raise PackTrustError("staged pack has conflicting signature material")
        if oci_archive.exists():
            if self._verify_oci_archive(oci_archive) != candidate_bytes:
                raise PackTrustError(
                    "staged pack does not match its signed OCI artifact"
                )
        elif bundle.exists():
            self._verify_signature(candidate, bundle)
        else:
            self._refuse_unsigned_if_unsafe()
        pack = self._load_one(candidate)
        if pack.backend != backend:
            raise PackTrustError("staged pack backend changed after operator review")
        result = self._activate_candidate(
            candidate,
            bundle if bundle.exists() else None,
            oci_archive if oci_archive.exists() else None,
            pack=pack,
            candidate_bytes=candidate_bytes,
        )
        candidate.unlink()
        bundle.unlink(missing_ok=True)
        oci_archive.unlink(missing_ok=True)
        return result

    def _rollback_sync(self, backend: BackendKind, version: str) -> PackInstallResult:
        retained = self.retained_path / backend.value / f"{_safe_version(version)}.json"
        if not retained.exists():
            raise PackTrustError("retained pack version does not exist")
        bundle = retained.with_suffix(".sigstore.json")
        oci_archive = retained.with_suffix(".oci.tar")
        if bundle.exists() and oci_archive.exists():
            raise PackTrustError("retained pack has conflicting signature material")
        if oci_archive.exists():
            if self._verify_oci_archive(oci_archive) != retained.read_bytes():
                raise PackTrustError(
                    "retained pack does not match its signed OCI artifact"
                )
        elif bundle.exists():
            self._verify_signature(retained, bundle)
        else:
            self._refuse_unsigned_if_unsafe()
        pack = self._load_one(retained)
        result = self._activate_candidate(
            retained,
            bundle if bundle.exists() else None,
            oci_archive if oci_archive.exists() else None,
            pack=pack,
            candidate_bytes=retained.read_bytes(),
        )
        self._repository.record_configuration_event_at_startup(
            "pack_rolled_back",
            {"backend": backend.value, "version": version, "digest": result.digest},
        )
        return result

    def _activate_candidate(
        self,
        candidate: Path,
        bundle: Path | None,
        oci_archive: Path | None,
        *,
        pack: BackendPack | None = None,
        candidate_bytes: bytes | None = None,
    ) -> PackInstallResult:
        pack = pack or self._load_one(candidate)
        content = (
            candidate_bytes if candidate_bytes is not None else candidate.read_bytes()
        )
        if hashlib.sha256(content).hexdigest() != pack.digest:
            raise PackTrustError("verified pack changed before activation")
        signed = bundle is not None or oci_archive is not None
        self._retain_current(pack.backend)
        destination = self.active_path / f"{pack.backend.value}.json"
        _atomic_private_write(destination, content)
        destination_bundle = destination.with_suffix(".sigstore.json")
        destination_oci = destination.with_suffix(".oci.tar")
        if bundle is not None:
            _atomic_private_write(destination_bundle, bundle.read_bytes())
            destination_oci.unlink(missing_ok=True)
        elif oci_archive is not None:
            _atomic_private_write(destination_oci, oci_archive.read_bytes())
            destination_bundle.unlink(missing_ok=True)
        else:
            destination_bundle.unlink(missing_ok=True)
            destination_oci.unlink(missing_ok=True)
            self._repository.set_pack_action_trust_at_startup(False)
        self._repository.set_restart_required_at_startup(True)
        self._repository.record_configuration_event_at_startup(
            "pack_installed",
            {
                "backend": pack.backend.value,
                "version": pack.version,
                "digest": pack.digest,
                "signed": signed,
            },
        )
        return _install_result(pack, signed=signed)

    def _retain_current(self, backend: BackendKind) -> None:
        current = self.active_path / f"{backend.value}.json"
        if not current.exists():
            return
        bundle = current.with_suffix(".sigstore.json")
        oci_archive = current.with_suffix(".oci.tar")
        try:
            if bundle.exists() and oci_archive.exists():
                raise PackTrustError(
                    "active pack has conflicting signature material"
                )
            if oci_archive.exists():
                if self._verify_oci_archive(oci_archive) != current.read_bytes():
                    raise PackTrustError(
                        "active pack does not match its signed OCI artifact"
                    )
            elif bundle.exists():
                self._verify_signature(current, bundle)
            pack = self._load_one(current)
        except PackTrustError:
            return
        destination_dir = self.retained_path / backend.value
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{_safe_version(pack.version)}.json"
        _atomic_private_write(destination, current.read_bytes())
        if bundle.exists():
            _atomic_private_write(
                destination.with_suffix(".sigstore.json"), bundle.read_bytes()
            )
            destination.with_suffix(".oci.tar").unlink(missing_ok=True)
        if oci_archive.exists():
            _atomic_private_write(
                destination.with_suffix(".oci.tar"), oci_archive.read_bytes()
            )
            destination.with_suffix(".sigstore.json").unlink(missing_ok=True)
        if not bundle.exists() and not oci_archive.exists():
            destination.with_suffix(".sigstore.json").unlink(missing_ok=True)
            destination.with_suffix(".oci.tar").unlink(missing_ok=True)

    def _verify_signature(self, pack_path: Path, bundle_path: Path) -> None:
        if not self.trust_root_path.is_file():
            raise PackTrustError("the shipped pack trust root is unavailable")
        command = [
            str(self.cosign_path),
            "verify-blob",
            "--bundle",
            str(bundle_path),
            "--certificate-identity",
            self.certificate_identity,
            "--certificate-oidc-issuer",
            self.certificate_issuer,
            "--trusted-root",
            str(self.trust_root_path),
            "--offline",
            "--",
            str(pack_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PackTrustError("cosign could not verify the pack") from exc
        if completed.returncode != 0:
            raise PackTrustError(
                "pack signature, workflow identity, or GitHub issuer verification failed"
            )

    def _verify_registry_reference(self, reference: str) -> None:
        if not self.trust_root_path.is_file():
            raise PackTrustError("the shipped pack trust root is unavailable")
        command = [
            str(self.cosign_path),
            "verify",
            "--certificate-identity",
            self.certificate_identity,
            "--certificate-oidc-issuer",
            self.certificate_issuer,
            "--trusted-root",
            str(self.trust_root_path),
            reference,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PackTrustError("cosign could not verify the registry pack") from exc
        if completed.returncode != 0:
            raise PackTrustError(
                "registry pack signature, workflow identity, or GitHub issuer "
                "verification failed"
            )

    def _save_oci_reference(self, reference: str, layout_path: Path) -> None:
        command = [
            str(self.cosign_path),
            "save",
            "--dir",
            str(layout_path),
            reference,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PackTrustError("cosign could not download the signed OCI pack") from exc
        if completed.returncode != 0:
            raise PackTrustError("the signed OCI pack could not be downloaded")

    def _verify_oci_archive(self, archive_path: Path) -> bytes:
        if archive_path.stat().st_size > MAX_OCI_LAYOUT_BYTES:
            raise PackTrustError("signed OCI pack archive exceeds the size limit")
        self.temp_path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.temp_path) as temporary:
            layout_path = Path(temporary) / "signed-pack"
            _extract_oci_layout(archive_path, layout_path)
            return self._verify_oci_layout(layout_path)

    def _verify_oci_layout(
        self,
        layout_path: Path,
        *,
        expected_manifest_digest: str | None = None,
    ) -> bytes:
        if not self.trust_root_path.is_file():
            raise PackTrustError("the shipped pack trust root is unavailable")
        command = [
            str(self.cosign_path),
            "verify",
            "--local-image",
            "--certificate-identity",
            self.certificate_identity,
            "--certificate-oidc-issuer",
            self.certificate_issuer,
            "--trusted-root",
            str(self.trust_root_path),
            str(layout_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PackTrustError("cosign could not verify the OCI pack") from exc
        if completed.returncode != 0:
            raise PackTrustError(
                "OCI pack signature, workflow identity, or GitHub issuer verification failed"
            )
        return _pack_bytes_from_oci_layout(
            layout_path,
            expected_manifest_digest=expected_manifest_digest,
        )

    def _refuse_unsigned_if_unsafe(self) -> None:
        if not self._repository.unsigned_packs_allowed_at_startup():
            raise PackTrustError("unsigned pack installation is disabled")
        if self._repository.has_actions_enabled_target_at_startup():
            raise PackTrustError(
                "unsigned packs are refused while any backend allows actions"
            )

    @staticmethod
    def _load_one(path: Path) -> BackendPack:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.json"
            candidate.write_bytes(path.read_bytes())
            try:
                packs = _load_pack_directory(candidate.parent, source_kind=None)
            except ValueError as exc:
                raise PackTrustError("pack file is invalid") from exc
        if len(packs) != 1:
            raise PackTrustError("pack file must declare one backend")
        return next(iter(packs.values()))

    @staticmethod
    def _load_bytes(content: bytes) -> BackendPack:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.json"
            candidate.write_bytes(content)
            return PackTrustManager._load_one(candidate)


async def _read_registry_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int,
    description: str,
) -> tuple[httpx.Headers, bytes, int]:
    """Read one registry response with bounded, HTTPS-only redirects."""

    current_url = httpx.URL(url)
    request_headers = dict(headers or {})
    for redirect_count in range(MAX_REGISTRY_REDIRECTS + 1):
        if current_url.scheme != "https":
            raise PackTrustError(
                f"{description} redirect refused a non-HTTPS destination"
            )
        async with client.stream(
            "GET",
            current_url,
            headers=request_headers,
            follow_redirects=False,
        ) as response:
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise PackTrustError(
                        f"{description} redirect did not include a destination"
                    )
                redirected_url = current_url.join(location)
                if redirected_url.scheme != "https":
                    raise PackTrustError(
                        f"{description} redirect refused a non-HTTPS destination"
                    )
                if (
                    redirected_url.host,
                    redirected_url.port,
                ) != (current_url.host, current_url.port):
                    request_headers = {
                        name: value
                        for name, value in request_headers.items()
                        if name.lower() != "authorization"
                    }
                current_url = redirected_url
                continue
            response.raise_for_status()
            advertised_length = response.headers.get("Content-Length")
            if advertised_length is not None:
                try:
                    if int(advertised_length) > max_bytes:
                        raise PackTrustError(
                            f"{description} exceeds the size limit"
                        )
                except ValueError as exc:
                    raise PackTrustError(
                        f"{description} has a malformed content length"
                    ) from exc
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > max_bytes:
                    raise PackTrustError(f"{description} exceeds the size limit")
                content.extend(chunk)
            return response.headers, bytes(content), redirect_count
    raise PackTrustError(f"{description} exceeded the redirect limit")


def _install_result(pack: BackendPack, *, signed: bool) -> PackInstallResult:
    definition_bytes = sum(
        len(tool.name) + len(tool.summary) + 32 * len(tool.arguments)
        for tool in pack.tools
    )
    return PackInstallResult(
        backend=pack.backend.value,
        version=pack.version,
        digest=pack.digest,
        tool_count=len(pack.tools),
        estimated_definition_tokens=max(1, definition_bytes // 4),
        signed=signed,
    )


def _safe_version(version: str) -> str:
    if not version or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in version
    ):
        raise PackTrustError("pack version is not filesystem-safe")
    return version


def _pack_tag_parts(tag: str) -> tuple[BackendKind, str] | None:
    for backend in sorted(BackendKind, key=lambda value: len(value.value), reverse=True):
        prefix = f"{PACK_TAG_PREFIX}{backend.value}-"
        if tag.startswith(prefix):
            return backend, tag.removeprefix(prefix)
    return None


def _version_sort_key(version: str) -> tuple[object, ...]:
    return tuple(
        (0, int(segment), "") if segment.isdigit() else (1, 0, segment)
        for segment in re.split(r"[._-]", version)
    )


async def _registry_pull_headers(client: httpx.AsyncClient) -> dict[str, str]:
    _, token_bytes, _ = await _read_registry_bytes(
        client,
        PACK_REGISTRY_TOKEN_URL,
        max_bytes=MAX_BUNDLE_BYTES,
        description="registry token response",
    )
    try:
        token = json.loads(token_bytes)["token"]
        if not isinstance(token, str) or not token:
            raise TypeError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PackTrustError("registry token response is malformed") from exc
    return {"Authorization": f"Bearer {token}"}


def _validated_sha256_digest(value: str) -> str:
    prefix = "sha256:"
    hexadecimal = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(hexadecimal) != 64
        or any(character not in "0123456789abcdef" for character in hexadecimal)
    ):
        raise PackTrustError("OCI digest is not a valid SHA-256 digest")
    return hexadecimal


def _sha256_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _pack_layer_from_manifest(content: bytes) -> dict[str, object]:
    try:
        document = json.loads(content)
        if (
            not isinstance(document, dict)
            or document.get("schemaVersion") != 2
            or document.get("mediaType") != OCI_MANIFEST_MEDIA_TYPE
            or document.get("artifactType") != PACK_ARTIFACT_TYPE
        ):
            raise TypeError
        layers = document["layers"]
        if not isinstance(layers, list) or len(layers) != 1:
            raise TypeError
        layer = layers[0]
        if (
            not isinstance(layer, dict)
            or layer.get("mediaType") != PACK_LAYER_MEDIA_TYPE
            or not isinstance(layer.get("size"), int)
            or int(layer["size"]) < 1
        ):
            raise TypeError
        _validated_sha256_digest(str(layer["digest"]))
        return dict(layer)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PackTrustError("OCI pack manifest is malformed") from exc


def _verify_blob_descriptor(
    content: bytes,
    descriptor: dict[str, object],
    *,
    limit: int,
) -> None:
    if not content or len(content) > limit or len(content) != int(descriptor["size"]):
        raise PackTrustError("OCI pack layer size does not match")
    if _sha256_digest(content) != str(descriptor["digest"]):
        raise PackTrustError("OCI pack layer digest does not match")


def _pack_bytes_from_oci_layout(
    layout_path: Path,
    *,
    expected_manifest_digest: str | None = None,
) -> bytes:
    try:
        index_bytes = (layout_path / "index.json").read_bytes()
        if len(index_bytes) > MAX_BUNDLE_BYTES:
            raise PackTrustError("OCI index exceeds the size limit")
        index = json.loads(index_bytes)
        manifests = index["manifests"]
        candidates = [
            descriptor
            for descriptor in manifests
            if isinstance(descriptor, dict)
            and descriptor.get("artifactType") == PACK_ARTIFACT_TYPE
        ]
        if len(candidates) != 1:
            raise TypeError
        manifest_descriptor = candidates[0]
        manifest_digest = str(manifest_descriptor["digest"])
        hexadecimal = _validated_sha256_digest(manifest_digest)
        if expected_manifest_digest is not None and manifest_digest != expected_manifest_digest:
            raise PackTrustError("downloaded OCI manifest digest changed")
        manifest_path = layout_path / "blobs" / "sha256" / hexadecimal
        manifest_bytes = manifest_path.read_bytes()
        if len(manifest_bytes) > MAX_BUNDLE_BYTES:
            raise PackTrustError("OCI pack manifest exceeds the size limit")
        if _sha256_digest(manifest_bytes) != manifest_digest:
            raise PackTrustError("saved OCI manifest digest does not match")
        layer = _pack_layer_from_manifest(manifest_bytes)
        layer_hexadecimal = _validated_sha256_digest(str(layer["digest"]))
        pack_bytes = (
            layout_path / "blobs" / "sha256" / layer_hexadecimal
        ).read_bytes()
        _verify_blob_descriptor(pack_bytes, layer, limit=MAX_PACK_BYTES)
        return pack_bytes
    except PackTrustError:
        raise
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PackTrustError("saved OCI pack layout is malformed") from exc


def _archive_oci_layout(layout_path: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in sorted(layout_path.rglob("*")):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise PackTrustError("saved OCI pack layout contains an unsafe file")
            archive.add(path, arcname=path.relative_to(layout_path), recursive=False)
    content = buffer.getvalue()
    if len(content) > MAX_OCI_LAYOUT_BYTES:
        raise PackTrustError("signed OCI pack archive exceeds the size limit")
    return content


def _extract_oci_layout(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            total_size = 0
            for member in members:
                parts = Path(member.name).parts
                if (
                    not parts
                    or member.name.startswith("/")
                    or ".." in parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise PackTrustError(
                        "signed OCI pack archive contains an unsafe entry"
                    )
                total_size += member.size
                if total_size > MAX_OCI_LAYOUT_BYTES:
                    raise PackTrustError(
                        "signed OCI pack archive expands beyond the size limit"
                    )
            archive.extractall(destination, members=members, filter="data")
    except PackTrustError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise PackTrustError("signed OCI pack archive is malformed") from exc


def _atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temporary).unlink(missing_ok=True)
        raise


def _validate_trust_root(content: bytes) -> None:
    try:
        document = json.loads(content)
        if not isinstance(document, dict) or not document.get("certificateAuthorities"):
            raise TypeError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PackTrustError("refreshed trust root is malformed") from exc
