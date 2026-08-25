"""Signed backend-pack verification, staging, rollback, and trust refresh."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from vcf_mcp.backend_packs import BackendPack, _load_pack_directory
from vcf_mcp.contracts import BackendKind
from vcf_mcp.runtime_repository import RuntimeRepository


PACK_CERTIFICATE_IDENTITY = (
    "https://github.com/sentania-labs/vcf-mcp/.github/workflows/"
    "release-packs.yml@refs/heads/main"
)
PACK_CERTIFICATE_ISSUER = "https://token.actions.githubusercontent.com"
PACK_FEED_URL = (
    "https://github.com/sentania-labs/vcf-mcp/releases/download/backend-packs/feed.json"
)
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
MAX_TRUST_ROOT_BYTES = 1024 * 1024


class PackTrustError(RuntimeError):
    """A pack was refused without exposing verifier output."""


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
            digest = hashlib.sha256(pack_path.read_bytes()).hexdigest()
            try:
                if bundle_path.exists():
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

    async def feed_catalog(self) -> tuple[dict[str, object], ...]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(PACK_FEED_URL)
            response.raise_for_status()
            content = response.content
        if len(content) > MAX_PACK_BYTES:
            raise PackTrustError("pack feed exceeds the size limit")
        try:
            document = json.loads(content)
            entries = document["packs"]
            if not isinstance(entries, list):
                raise TypeError
            return tuple(dict(entry) for entry in entries if isinstance(entry, dict))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PackTrustError("pack feed is malformed") from exc

    async def install_from_feed(self, entry_id: str) -> PackInstallResult:
        entries = await self.feed_catalog()
        entry = next(
            (
                candidate
                for candidate in entries
                if str(candidate.get("id")) == entry_id
            ),
            None,
        )
        if entry is None:
            raise PackTrustError("pack feed selection is no longer available")
        pack_url = str(entry.get("pack_url", ""))
        bundle_url = str(entry.get("bundle_url", ""))
        if not pack_url.startswith("https://") or not bundle_url.startswith("https://"):
            raise PackTrustError("pack feed URLs must use HTTPS")
        async with httpx.AsyncClient(timeout=30.0) as client:
            pack_response, bundle_response = await asyncio.gather(
                client.get(pack_url), client.get(bundle_url)
            )
            pack_response.raise_for_status()
            bundle_response.raise_for_status()
        return await self.install_manual(pack_response.content, bundle_response.content)

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
            self.staged_path.mkdir(parents=True, exist_ok=True)
            destination = self.staged_path / f"{pack.backend.value}.json"
            _atomic_private_write(destination, pack_bytes)
            destination_bundle = destination.with_suffix(".sigstore.json")
            if signed:
                _atomic_private_write(destination_bundle, bundle_bytes or b"")
            else:
                destination_bundle.unlink(missing_ok=True)
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
        signed = bundle.exists()
        if signed:
            self._verify_signature(candidate, bundle)
        else:
            self._refuse_unsigned_if_unsafe()
        pack = self._load_one(candidate)
        if pack.backend != backend:
            raise PackTrustError("staged pack backend changed after operator review")
        result = self._activate_candidate(
            candidate,
            bundle if signed else None,
            pack=pack,
            candidate_bytes=candidate_bytes,
        )
        candidate.unlink()
        bundle.unlink(missing_ok=True)
        return result

    def _rollback_sync(self, backend: BackendKind, version: str) -> PackInstallResult:
        retained = self.retained_path / backend.value / f"{_safe_version(version)}.json"
        if not retained.exists():
            raise PackTrustError("retained pack version does not exist")
        bundle = retained.with_suffix(".sigstore.json")
        if bundle.exists():
            self._verify_signature(retained, bundle)
        else:
            self._refuse_unsigned_if_unsafe()
        pack = self._load_one(retained)
        result = self._activate_candidate(
            retained,
            bundle if bundle.exists() else None,
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
        signed = bundle is not None
        self._retain_current(pack.backend)
        destination = self.active_path / f"{pack.backend.value}.json"
        _atomic_private_write(destination, content)
        destination_bundle = destination.with_suffix(".sigstore.json")
        if bundle is not None:
            _atomic_private_write(destination_bundle, bundle.read_bytes())
        else:
            destination_bundle.unlink(missing_ok=True)
            self._repository.set_pack_action_trust_at_startup(False)
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
        try:
            if bundle.exists():
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

    def _verify_signature(self, pack_path: Path, bundle_path: Path) -> None:
        if not self.trust_root_path.is_file():
            raise PackTrustError("the shipped pack trust root is unavailable")
        command = [
            str(self.cosign_path),
            "verify-blob",
            "--bundle",
            str(bundle_path),
            "--certificate-identity",
            PACK_CERTIFICATE_IDENTITY,
            "--certificate-oidc-issuer",
            PACK_CERTIFICATE_ISSUER,
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
            packs = _load_pack_directory(candidate.parent, source_kind=None)
        if len(packs) != 1:
            raise PackTrustError("pack file must declare one backend")
        return next(iter(packs.values()))


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
