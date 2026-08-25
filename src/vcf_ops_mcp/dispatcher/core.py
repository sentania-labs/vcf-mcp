"""Ordered dispatcher implementation."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from vcf_ops_mcp.contracts import (
    AuditRecord,
    AuditRepository,
    AuditStatus,
    CapabilityName,
    CorrelationId,
    MUTATING,
    ResponseEnvelope,
    TargetId,
    TargetPosture,
    TargetRepository,
    TerminalState,
    ToolContext,
    ToolSpec,
    RequestIdentity,
    extract_request_identity,
)

from .errors import DispatchError
from .registry import ToolRegistry
from .reservations import FreeSpaceReservations, InsufficientAuditSpace


@dataclass(frozen=True, slots=True)
class DispatchDependencies:
    targets: TargetRepository
    audit: AuditRepository
    global_scopes: frozenset[CapabilityName]
    digest_key: bytes
    mutating: frozenset[CapabilityName] = MUTATING
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    reservations: FreeSpaceReservations | None = None
    endpoint_name: str = "ops"
    enforce_endpoint_target: bool = True
    pack_id: str | None = None
    pack_digest: str | None = None
    pack_version: str | None = None


class Dispatcher:
    """Apply authorization, audit ordering, deadline, and result projection."""

    def __init__(
        self,
        registry: ToolRegistry,
        dependencies: DispatchDependencies,
    ) -> None:
        self._registry = registry
        self._dependencies = dependencies

    async def dispatch(
        self,
        tool_name: str,
        *,
        context: ToolContext,
        target_id: TargetId,
        arguments: Mapping[str, object],
        deadline_seconds: float,
    ) -> ResponseEnvelope:
        spec = self._registry.get(tool_name)
        identity = extract_request_identity(context)
        correlation_id = CorrelationId(str(uuid.uuid4()))
        digest = self._arguments_digest(arguments)
        if self._dependencies.endpoint_name not in identity.allowed_endpoints:
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "endpoint_not_allowed",
                "API key is not allowed on this endpoint",
            )
        if identity.revoked:
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "key_revoked",
                "API key is revoked",
            )
        if target_id not in identity.allowed_targets:
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "target_not_allowed",
                "target is not allowed",
            )

        target = await self._dependencies.targets.get(target_id)
        if target is None:
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "target_not_found",
                "target does not exist",
            )
        if (
            self._dependencies.enforce_endpoint_target
            and target.backend.value != self._dependencies.endpoint_name
        ):
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "endpoint_target_mismatch",
                "target belongs to a different backend endpoint",
            )
        effective_scopes = identity.granted_scopes & self._dependencies.global_scopes
        if (
            spec.capability not in effective_scopes
            or spec.key_scope not in effective_scopes
        ):
            await self._deny(
                spec,
                correlation_id,
                identity,
                target_id,
                digest,
                "scope_denied",
                "tool scope is not granted",
            )
        if spec.capability in self._dependencies.mutating:
            if target.is_prod:
                await self._deny(
                    spec,
                    correlation_id,
                    identity,
                    target_id,
                    digest,
                    "prod_actions_forbidden",
                    "production targets cannot execute actions",
                )
            if target.posture is not TargetPosture.ACTIONS_ENABLED:
                await self._deny(
                    spec,
                    correlation_id,
                    identity,
                    target_id,
                    digest,
                    "target_read_only",
                    "target does not permit actions",
                )

        started_at = self._dependencies.clock()
        lease = None
        if self._dependencies.reservations is not None:
            try:
                lease = await self._dependencies.reservations.acquire()
            except InsufficientAuditSpace:
                await self._deny(
                    spec,
                    correlation_id,
                    identity,
                    target_id,
                    digest,
                    "audit_space_exhausted",
                    "audit free-space reservation is unavailable",
                )
        attempt = self._record(
            spec,
            correlation_id,
            identity,
            target_id,
            digest,
            AuditStatus.ATTEMPT,
            started_at,
        )
        try:
            await self._dependencies.audit.append_committed(attempt)
        except Exception as exc:
            if lease is not None:
                await lease.release()
            raise DispatchError(
                "audit_attempt_write_failed",
                "audit attempt could not be committed",
            ) from exc

        monotonic_start = time.monotonic()
        payload: object = None
        state = TerminalState.OK
        status = AuditStatus.OK
        error_code: str | None = None
        cancellation: asyncio.CancelledError | None = None
        try:
            payload = await asyncio.wait_for(
                spec.audited_handler(target, arguments),
                timeout=deadline_seconds,
            )
        except TimeoutError:
            state = TerminalState.TIMEOUT
            status = AuditStatus.TIMEOUT
            error_code = "handler_timeout"
        except Exception:
            state = TerminalState.ERROR
            status = AuditStatus.ERROR
            error_code = "handler_error"
        except asyncio.CancelledError as exc:
            status = AuditStatus.CANCELLED
            error_code = "handler_cancelled"
            cancellation = exc

        terminal = self._record(
            spec,
            correlation_id,
            identity,
            target_id,
            digest,
            status,
            self._dependencies.clock(),
            error_code=error_code,
            latency_ms=max(0, round((time.monotonic() - monotonic_start) * 1000)),
        )
        try:
            try:
                await self._dependencies.audit.append_committed(terminal)
            except Exception:
                if cancellation is None:
                    return ResponseEnvelope(
                        state=TerminalState.OUTCOME_UNKNOWN,
                        outcome_unknown_payload=payload,
                        error_code="audit_terminal_write_failed",
                        retryable=False,
                        message="handler outcome could not be durably recorded",
                    )
        finally:
            if lease is not None:
                await lease.release()

        if cancellation is not None:
            raise cancellation
        if state is TerminalState.OK:
            return ResponseEnvelope(state=state, success=payload)
        return ResponseEnvelope(
            state=state,
            error_code=error_code,
            retryable=False,
        )

    async def _deny(
        self,
        spec: ToolSpec,
        correlation_id: CorrelationId,
        identity: RequestIdentity,
        target_id: TargetId,
        digest: str,
        error_code: str,
        message: str,
    ) -> NoReturn:
        denied = self._record(
            spec,
            correlation_id,
            identity,
            target_id,
            digest,
            AuditStatus.DENIED,
            self._dependencies.clock(),
            error_code=error_code,
        )
        try:
            await self._dependencies.audit.append_committed(denied)
        except Exception as exc:
            raise DispatchError(
                "audit_denial_write_failed",
                "audit denial could not be committed",
            ) from exc
        raise DispatchError(error_code, message)

    def _arguments_digest(self, arguments: Mapping[str, object]) -> str:
        canonical = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        return hmac.new(
            self._dependencies.digest_key,
            canonical,
            hashlib.sha256,
        ).hexdigest()

    def _record(
        self,
        spec: ToolSpec,
        correlation_id: CorrelationId,
        identity: RequestIdentity,
        target_id: TargetId,
        digest: str,
        status: AuditStatus,
        timestamp: datetime,
        *,
        error_code: str | None = None,
        latency_ms: int | None = None,
    ) -> AuditRecord:
        return AuditRecord(
            correlation_id=correlation_id,
            key_id=identity.key_id,
            target_id=target_id,
            tool_name=spec.name,
            arguments_digest=digest,
            status=status,
            timestamp=timestamp,
            error_code=error_code,
            latency_ms=latency_ms,
            projection_version=spec.projection,
            caller_id=identity.caller_id,
            endpoint_name=self._dependencies.endpoint_name,
            pack_id=self._dependencies.pack_id,
            pack_digest=self._dependencies.pack_digest,
            pack_version=self._dependencies.pack_version,
        )
