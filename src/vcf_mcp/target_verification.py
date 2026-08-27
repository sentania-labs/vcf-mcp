"""Audited, bounded verification of submitted backend credentials."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum

from vcf_mcp.backend_packs import BackendPack
from vcf_mcp.contracts import (
    AuditRecord,
    AuditRepository,
    AuditStatus,
    BackendKind,
    CorrelationId,
    KeyId,
    TargetRecord,
)
from vcf_mcp.declared_backend import DeclaredBackendClient
from vcf_mcp.vcf.client import TargetCredentials
from vcf_mcp.vcf.errors import (
    AuthenticationError,
    PermissionDeniedError,
    TlsVerificationError,
    UpstreamConnectionError,
    UpstreamProtocolError,
    UpstreamResolutionError,
    UpstreamStatusError,
    UpstreamTimeoutError,
    VcfError,
)


VERIFICATION_TIMEOUT_SECONDS = 15.0
CONSOLE_ADMIN_KEY_ID = KeyId("console-admin")
VERIFICATION_TOOL_NAME = "console_verify_target"
VERIFICATION_PROJECTION = "target-verification-v1"


class VerificationFailureCause(StrEnum):
    CANNOT_RESOLVE = "cannot_resolve"
    CANNOT_CONNECT = "cannot_connect"
    TIMEOUT = "timeout"
    CERTIFICATE_NOT_TRUSTED = "certificate_not_trusted"
    CREDENTIAL_REJECTED = "credential_rejected"
    UNEXPECTED_RESPONSE = "unexpected_response"


_FAILURE_MESSAGES = {
    VerificationFailureCause.CANNOT_RESOLVE: (
        "Cannot resolve the backend hostname. Nothing was saved. Check DNS and "
        "the FQDN, then retry."
    ),
    VerificationFailureCause.CANNOT_CONNECT: (
        "Cannot connect to the backend. Nothing was saved. Check routing, "
        "firewall policy, service availability, and retry."
    ),
    VerificationFailureCause.TIMEOUT: (
        "Backend verification timed out after {timeout_seconds} seconds. "
        "Nothing was saved. Check backend responsiveness and the network path, "
        "then retry."
    ),
    VerificationFailureCause.CERTIFICATE_NOT_TRUSTED: (
        "The backend certificate is not trusted. Nothing was saved. Install "
        "its issuer as the appliance CA or a target-specific CA, then retry."
    ),
    VerificationFailureCause.CREDENTIAL_REJECTED: (
        "The backend rejected the credential. Nothing was saved. Check the "
        "username, password, authentication source, and retry."
    ),
    VerificationFailureCause.UNEXPECTED_RESPONSE: (
        "The backend was reachable but returned an unexpected response. "
        "Nothing was saved. Confirm the selected product, endpoint, and the "
        "credential's read permission, then retry."
    ),
}


class TargetVerificationError(ValueError):
    """A submitted target failed an operator-actionable verification check."""

    def __init__(
        self,
        cause: VerificationFailureCause,
        *,
        timeout_seconds: float = VERIFICATION_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            _FAILURE_MESSAGES[cause].format(timeout_seconds=f"{timeout_seconds:g}")
        )
        self.cause = cause


class TargetVerificationUnavailable(RuntimeError):
    """Verification could not meet its durable audit requirement."""


TargetClientFactory = Callable[
    [TargetRecord, TargetCredentials, BackendPack, str | None],
    DeclaredBackendClient,
]


def _default_client_factory(
    target: TargetRecord,
    credentials: TargetCredentials,
    pack: BackendPack,
    root_ca_pem: str | None,
) -> DeclaredBackendClient:
    return DeclaredBackendClient(
        target=target,
        credentials=credentials,
        pack=pack,
        root_ca_pem=root_ca_pem,
    )


class TargetVerifier:
    """Run the read probe declared by a backend pack and audit its outcome."""

    def __init__(
        self,
        *,
        packs: Mapping[BackendKind, BackendPack],
        audit_repository: AuditRepository,
        client_factory: TargetClientFactory = _default_client_factory,
        timeout_seconds: float = VERIFICATION_TIMEOUT_SECONDS,
    ) -> None:
        self._packs = packs
        self._audit = audit_repository
        self._client_factory = client_factory
        self._timeout_seconds = timeout_seconds

    async def verify(
        self,
        *,
        target: TargetRecord,
        credentials: TargetCredentials,
        root_ca_pem: str | None,
    ) -> datetime:
        pack = self._packs.get(target.backend)
        if pack is None:
            raise TargetVerificationError(
                VerificationFailureCause.UNEXPECTED_RESPONSE
            )
        correlation_id = CorrelationId(str(uuid.uuid4()))
        digest = _verification_digest(target)
        started_at = datetime.now(UTC)
        started = time.monotonic()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_seconds
        terminal_audit_budget = min(5.0, self._timeout_seconds / 3)
        probe_deadline = deadline - terminal_audit_budget
        await self._append_before(
            _audit_record(
                target=target,
                pack=pack,
                correlation_id=correlation_id,
                digest=digest,
                status=AuditStatus.ATTEMPT,
                timestamp=started_at,
            ),
            deadline=deadline,
        )

        failure: TargetVerificationError | None = None
        audit_status = AuditStatus.OK
        try:
            async with asyncio.timeout_at(probe_deadline):
                client = self._client_factory(
                    target, credentials, pack, root_ca_pem
                )
                try:
                    await client.request_declared(
                        pack.verification_probe.tool,
                        pack.verification_probe.arguments,
                    )
                finally:
                    await client.aclose()
        except TimeoutError:
            failure = TargetVerificationError(
                VerificationFailureCause.TIMEOUT,
                timeout_seconds=self._timeout_seconds,
            )
            audit_status = AuditStatus.TIMEOUT
        except VcfError as exc:
            failure = _operator_failure(
                exc, timeout_seconds=self._timeout_seconds
            )
            audit_status = exc.audit_status
        except (TypeError, ValueError):
            failure = TargetVerificationError(
                VerificationFailureCause.UNEXPECTED_RESPONSE
            )
            audit_status = AuditStatus.ERROR

        completed_at = datetime.now(UTC)
        await self._append_before(
            _audit_record(
                target=target,
                pack=pack,
                correlation_id=correlation_id,
                digest=digest,
                status=audit_status,
                timestamp=completed_at,
                error_code=(
                    None
                    if failure is None
                    else f"target_verification_{failure.cause.value}"
                ),
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            ),
            deadline=deadline,
        )
        if failure is not None:
            raise failure
        return completed_at

    async def _append_before(self, record: AuditRecord, *, deadline: float) -> None:
        try:
            async with asyncio.timeout_at(deadline):
                await self._audit.append_committed(record)
        except Exception as exc:
            raise TargetVerificationUnavailable(
                "Target verification audit is unavailable. Nothing was saved."
            ) from exc


def _operator_failure(
    exc: VcfError, *, timeout_seconds: float
) -> TargetVerificationError:
    if isinstance(exc, AuthenticationError):
        cause = VerificationFailureCause.CREDENTIAL_REJECTED
    elif isinstance(exc, UpstreamResolutionError):
        cause = VerificationFailureCause.CANNOT_RESOLVE
    elif isinstance(exc, UpstreamTimeoutError):
        cause = VerificationFailureCause.TIMEOUT
    elif isinstance(exc, UpstreamConnectionError):
        cause = VerificationFailureCause.CANNOT_CONNECT
    elif isinstance(exc, TlsVerificationError):
        cause = VerificationFailureCause.CERTIFICATE_NOT_TRUSTED
    elif isinstance(
        exc,
        (PermissionDeniedError, UpstreamProtocolError, UpstreamStatusError),
    ):
        cause = VerificationFailureCause.UNEXPECTED_RESPONSE
    else:
        cause = VerificationFailureCause.UNEXPECTED_RESPONSE
    return TargetVerificationError(cause, timeout_seconds=timeout_seconds)


def _verification_digest(target: TargetRecord) -> str:
    public_arguments = {
        "backend": target.backend.value,
        "fqdn": target.fqdn,
        "target_id": str(target.id),
        "verify_ssl": target.verify_ssl,
    }
    encoded = json.dumps(
        public_arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _audit_record(
    *,
    target: TargetRecord,
    pack: BackendPack,
    correlation_id: CorrelationId,
    digest: str,
    status: AuditStatus,
    timestamp: datetime,
    error_code: str | None = None,
    latency_ms: int | None = None,
) -> AuditRecord:
    return AuditRecord(
        correlation_id=correlation_id,
        key_id=CONSOLE_ADMIN_KEY_ID,
        target_id=target.id,
        tool_name=VERIFICATION_TOOL_NAME,
        arguments_digest=digest,
        status=status,
        timestamp=timestamp,
        error_code=error_code,
        latency_ms=latency_ms,
        projection_version=VERIFICATION_PROJECTION,
        endpoint_name=pack.endpoint,
        pack_id=pack.pack_id,
        pack_digest=pack.digest,
        pack_version=pack.version,
        authorization_mode="console",
        key_owner="admin",
    )
