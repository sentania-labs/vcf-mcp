"""Shared contracts for the Phase 1 policy, read, and delivery slices.

This module contains values and interfaces only. It performs no I/O and has no
dependency on the MCP framework, a database, or a VCF Ops client.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType, Protocol, TypeAlias, runtime_checkable


TargetId = NewType("TargetId", str)
KeyId = NewType("KeyId", str)
CorrelationId = NewType("CorrelationId", str)
ConfigurationGeneration = NewType("ConfigurationGeneration", int)
JsonObject: TypeAlias = Mapping[str, object]


class Capability(StrEnum):
    """Semantic scopes grantable by registered Phase 1 adapters."""

    READ_INVENTORY = "read:inventory"
    READ_METRICS = "read:metrics"
    READ_ALERTS = "read:alerts"
    READ_REPORTS = "read:reports"
    READ_NETWORK = "read:network"
    READ_LIFECYCLE = "read:lifecycle"
    READ_LOGS = "read:logs"
    READ_PROTECTION = "read:protection"
    READ_SKILLS = "read:skills"
    READ_TARGETS = "read:targets"


# Production has no mutating capability in Phase 1. Tests may construct a
# separate registry with a synthetic capability string to exercise the gate.
CapabilityName: TypeAlias = Capability | str
MUTATING: frozenset[CapabilityName] = frozenset()
TEST_ONLY_MUTATING_CAPABILITY: CapabilityName = "test:mutating"
"""Synthetic capability for a test-scoped registry and mutating set only."""


class TargetPosture(StrEnum):
    READ_ONLY = "read_only"
    ACTIONS_ENABLED = "actions_enabled"


class AuthorizationMode(StrEnum):
    """Instance-wide API-key policy selected in the admin interface."""

    LOCAL = "local"
    GATEWAY = "gateway"


class BackendKind(StrEnum):
    """Static backend identities understood by the appliance."""

    OPS = "ops"
    VCENTER = "vcenter"
    NSX = "nsx"
    SDDC_MANAGER = "sddc-manager"
    OPS_NETWORKS = "ops-networks"
    FLEET_LCM = "fleet-lcm"
    SDDC_LCM = "sddc-lcm"
    LOG_MANAGEMENT = "log-management"
    VSAN_DP = "vsan-dp"
    AVI = "avi"
    AUTOMATION = "automation"
    IDENTITY_BROKER = "identity-broker"
    SOFTWARE_DEPOT = "software-depot"


@dataclass(frozen=True, slots=True)
class TargetRecord:
    """Public target configuration, excluding every credential and token."""

    id: TargetId
    name: str
    fqdn: str
    posture: TargetPosture
    is_prod: bool
    verify_ssl: bool
    auth_source: str
    configuration_generation: ConfigurationGeneration
    backend: BackendKind = BackendKind.OPS
    has_custom_ca: bool = False
    is_usable: bool = True
    unusable_reason: str | None = None
    auth_failure_count: int = 0
    auth_locked: bool = False
    last_verified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EffectiveTargetTrust:
    """Resolved CA trust for one target, available before any live request."""

    root_ca_pem: str | None
    global_ca_fingerprints: tuple[str, ...] = ()
    target_ca_fingerprints: tuple[str, ...] = ()
    global_ca_configured: bool = False
    target_ca_configured: bool = False
    target_ca_available: bool = True

    @property
    def uses_global_ca(self) -> bool:
        return self.global_ca_configured

    @property
    def uses_target_ca(self) -> bool:
        return self.target_ca_configured and self.target_ca_available


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    """Immutable API-key identity resolved independently for one HTTP request."""

    key_id: KeyId
    granted_scopes: frozenset[CapabilityName]
    allowed_targets: frozenset[TargetId]
    revoked: bool = False
    allowed_endpoints: frozenset[str] = frozenset({BackendKind.OPS.value})
    caller_id: str | None = None
    authorization_mode: AuthorizationMode = AuthorizationMode.LOCAL
    owner: str | None = None


@runtime_checkable
class RequestState(Protocol):
    """The dedicated request-state attribute populated by HTTP middleware."""

    identity: RequestIdentity | None


@runtime_checkable
class HttpRequest(Protocol):
    state: RequestState


@runtime_checkable
class RequestContext(Protocol):
    request: HttpRequest | None


@runtime_checkable
class ToolContext(Protocol):
    """Minimum injected context accepted by the dispatcher.

    Read identity only from ``request_context.request.state.identity``. Deny
    with a typed error if ``request`` is None, ``identity`` is absent, or its
    value is not a ``RequestIdentity``. Never read identity from a module
    global and never cache identity on a session.
    """

    @property
    def request_context(self) -> RequestContext: ...


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"


@dataclass(frozen=True, slots=True)
class OutboundContract:
    method: HttpMethod
    path_template: str
    permitted_query_parameters: frozenset[str]


ToolHandler: TypeAlias = Callable[..., Awaitable[JsonObject]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Validated view of the required registration core."""

    schema_version: int
    name: str
    capability: CapabilityName
    key_scope: CapabilityName
    target_policy: str
    argument_digest_policy: str
    projection: str
    outbound_contract: OutboundContract
    audited_handler: ToolHandler
    extensions: Mapping[str, object]


REGISTRATION_SCHEMA_VERSION = 1
REQUIRED_REGISTRATION_CORE: frozenset[str] = frozenset(
    {
        "schema_version",
        "name",
        "capability",
        "key_scope",
        "target_policy",
        "argument_digest_policy",
        "projection",
        "outbound_contract",
        "audited_handler",
    }
)
RegistrationMapping: TypeAlias = Mapping[str, object]
"""Open versioned tool registration record.

Every record must contain ``REQUIRED_REGISTRATION_CORE`` and use
``REGISTRATION_SCHEMA_VERSION``. Additional fields are additive and must use a
family-qualified key such as ``metrics.sample_cap``. Readers must ignore
unknown qualified keys. A core key may change meaning or type only in a new
schema version. This rule lets one family extend its declaration without an
edit to this shared contract.
"""


class TerminalState(StrEnum):
    OK = "ok"
    DENIED = "denied"
    ERROR = "error"
    TIMEOUT = "timeout"
    OUTCOME_UNKNOWN = "outcome_unknown"


NO_PAYLOAD: Final = object()
"""Sentinel distinguishing an absent payload from a payload of literal None."""


@dataclass(frozen=True, slots=True)
class ResponseEnvelope:
    """Dispatcher response with unknown-outcome data outside the success arm."""

    state: TerminalState
    success: object = NO_PAYLOAD
    outcome_unknown_payload: object = NO_PAYLOAD
    error_code: str | None = None
    retryable: bool = False
    message: str | None = None

    def __post_init__(self) -> None:
        if self.state is TerminalState.OUTCOME_UNKNOWN:
            if (
                self.success is not NO_PAYLOAD
                or self.outcome_unknown_payload is NO_PAYLOAD
            ):
                raise ValueError(
                    "outcome_unknown requires only outcome_unknown_payload"
                )
            if self.retryable:
                raise ValueError("outcome_unknown prohibits automatic retry")
        elif self.outcome_unknown_payload is not NO_PAYLOAD:
            raise ValueError("outcome_unknown_payload requires outcome_unknown state")


class AuditStatus(StrEnum):
    ATTEMPT = "attempt"
    OK = "ok"
    DENIED = "denied"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    correlation_id: CorrelationId
    key_id: KeyId
    target_id: TargetId
    tool_name: str
    arguments_digest: str
    status: AuditStatus
    timestamp: datetime
    error_code: str | None = None
    latency_ms: int | None = None
    projection_version: str | None = None
    skill_content_digest: str | None = None
    caller_id: str | None = None
    endpoint_name: str | None = None
    pack_id: str | None = None
    pack_digest: str | None = None
    pack_version: str | None = None
    authorization_mode: str | None = None
    key_owner: str | None = None


class IdentityDeny(Exception):
    """Typed, auditable denial raised when request identity is unavailable."""

    error_code = "request_identity_missing_or_invalid"
    audit_status = AuditStatus.DENIED


def extract_request_identity(context: ToolContext) -> RequestIdentity:
    """Extract request-local identity or raise an auditable typed denial."""

    request = context.request_context.request
    if request is None:
        raise IdentityDeny
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, RequestIdentity):
        raise IdentityDeny
    return identity


class TargetRepository(Protocol):
    async def get(self, target_id: TargetId) -> TargetRecord | None: ...

    async def list(self) -> tuple[TargetRecord, ...]: ...

    async def save(
        self,
        target: TargetRecord,
        *,
        expected_generation: ConfigurationGeneration | None,
    ) -> TargetConfigurationChange: ...


class AuditRepository(Protocol):
    """Durable audit storage, including startup reconciliation.

    Counts and enumeration must be derived from committed storage. Recovery
    closes every attempt lacking a terminal record as ``outcome_unknown`` and
    returns the number closed. It must never infer a successful outcome.
    """

    async def append_committed(self, record: AuditRecord) -> None: ...

    async def is_writable(self) -> bool: ...

    async def unreconciled_attempt_count(self) -> int: ...

    async def unreconciled_attempts(self) -> tuple[AuditRecord, ...]: ...

    async def close_unreconciled_attempts(self, *, recovered_at: datetime) -> int: ...


class ApiKeyScopeRepository(Protocol):
    async def resolve_request_identity(
        self, presented_key: str
    ) -> RequestIdentity | None:
        """Digest and compare a presented key in constant time."""
        ...

    async def grantable_scopes(self) -> frozenset[CapabilityName]: ...


class InvalidationMode(StrEnum):
    """How already-started work on the superseded client is completed."""

    DRAIN = "drain"
    CANCEL = "cancel"


def invalidation_mode_for_change(
    previous: TargetRecord, current: TargetRecord
) -> InvalidationMode:
    """Cancel in-flight work when an edit tightens TLS verification."""

    if not previous.verify_ssl and current.verify_ssl:
        return InvalidationMode.CANCEL
    return InvalidationMode.DRAIN


@dataclass(frozen=True, slots=True)
class TargetConfigurationChange:
    """Monotonic target edit event returned by the target repository."""

    target_id: TargetId
    previous_generation: ConfigurationGeneration
    current_generation: ConfigurationGeneration

    def __post_init__(self) -> None:
        if self.current_generation <= self.previous_generation:
            raise ValueError("target configuration generation must increase")


@dataclass(frozen=True, slots=True)
class InvalidationResult:
    """Proof that invalidation reached its completion barrier."""

    change: TargetConfigurationChange
    mode: InvalidationMode
    drained_requests: int
    cancelled_requests: int

    def __post_init__(self) -> None:
        if self.drained_requests < 0 or self.cancelled_requests < 0:
            raise ValueError("request counts cannot be negative")
        if self.mode is InvalidationMode.DRAIN and self.cancelled_requests:
            raise ValueError("drain mode cannot report cancelled requests")


class TargetClientInvalidator(Protocol):
    """Invalidation barrier shared by admin writes and the client registry.

    The admin edit flow must await this method after ``TargetRepository.save``
    and before reporting success. On entry, the registry atomically marks the
    client for ``previous_generation`` closed so it accepts no new work. Before
    returning, DRAIN waits for its in-flight work to finish and CANCEL cancels
    and awaits it. The registry then removes that client. A later lookup may
    lazily create only a client for ``current_generation``.

    Every consumer snapshots ``TargetRecord.configuration_generation`` before
    I/O and compares it with the repository generation before retry and before
    returning a result. A mismatch discards the old result and must not retry
    through the closed client.
    """

    async def invalidate(
        self,
        change: TargetConfigurationChange,
        *,
        mode: InvalidationMode,
    ) -> InvalidationResult: ...
