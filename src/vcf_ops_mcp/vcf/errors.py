"""Typed error hierarchy for the VCF read plane.

Every error carries a stable ``error_code`` that the dispatcher writes to the
audit record, an ``audit_status`` selecting the terminal audit state, and a
``retryable`` flag the response envelope reports to the caller.

Two rules hold for every class here:

1. No credential, token, password, or raw response body is ever placed in an
   exception message. Messages name endpoints, status codes, caps, and target
   ids only. ``tests/test_vcf_errors.py`` asserts this for the paths that
   handle secret material.
2. An error code is part of the tool contract. Renaming one is a client-visible
   change, not a refactor.
"""

from __future__ import annotations

from vcf_ops_mcp.contracts import AuditStatus, TargetId


class VcfError(Exception):
    """Base of every error raised by the read plane."""

    error_code = "vcf_error"
    audit_status: AuditStatus = AuditStatus.ERROR
    retryable = False

    def __init__(self, message: str, *, target_id: TargetId | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.target_id = target_id


class TargetConfigurationError(VcfError):
    """A registered target cannot be used as configured."""

    error_code = "vcf_target_configuration_invalid"
    audit_status = AuditStatus.DENIED


class AuthenticationError(VcfError):
    """Token acquisition was refused by the appliance.

    A wrong auth source and a wrong password are byte-identical 401s on this
    API, so this error never claims to know which one it was.
    """

    error_code = "vcf_authentication_failed"
    audit_status = AuditStatus.DENIED


class ReauthenticationExhausted(AuthenticationError):
    """A freshly acquired token was itself refused with 401.

    This is the terminal state of the per-request retry counter. It is a
    distinct code because it is the observable signature of mid-session
    credential revocation, and treating it as an ordinary auth failure hides
    the one case where retrying is guaranteed to loop.
    """

    error_code = "vcf_reauthentication_exhausted"


class PermissionDeniedError(VcfError):
    """The appliance returned 403. The credential is valid and lacks the role.

    Re-authentication never fires on this path. A client that treats an
    auth-ish non-2xx as expiry burns an acquire on every call forever.
    """

    error_code = "vcf_permission_denied"
    audit_status = AuditStatus.DENIED

    def __init__(
        self,
        message: str,
        *,
        target_id: TargetId | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message, target_id=target_id)
        self.path = path


class UpstreamStatusError(VcfError):
    """A non-2xx response that is neither 401 nor 403."""

    error_code = "vcf_upstream_status"

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        target_id: TargetId | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message, target_id=target_id)
        self.status_code = status_code
        self.path = path


class UpstreamProtocolError(VcfError):
    """A 2xx response whose body is not the JSON shape the adapter requires.

    The appliance answers an invalid token with JSON and a bad auth scheme with
    HTML, so body decoding never assumes JSON.
    """

    error_code = "vcf_upstream_protocol"


class UpstreamTimeoutError(VcfError):
    """The request exceeded one of the explicit client timeouts."""

    error_code = "vcf_upstream_timeout"
    audit_status = AuditStatus.TIMEOUT
    retryable = True


class UpstreamUnavailableError(VcfError):
    """The appliance could not be reached at all."""

    error_code = "vcf_upstream_unavailable"
    retryable = True


class TlsVerificationError(VcfError):
    """The target's certificate failed verification for that target's policy.

    Never downgraded automatically. A target registered with verification on
    that then fails verification is a security event, not a transient fault.
    """

    error_code = "vcf_tls_verification_failed"


class OutboundContractViolation(VcfError):
    """Tool code attempted an HTTP call outside the frozen allowlist.

    Raised before any socket work. The parameter half of the allowlist is
    load-bearing: this appliance silently ignores an unrecognized query
    parameter and answers 200 with the whole unfiltered collection.
    """

    error_code = "vcf_outbound_contract_violation"
    audit_status = AuditStatus.DENIED


class ResultCapExceeded(VcfError):
    """A read was refused because it exceeds a declared cap.

    Refusal, never truncation. The message names the cap and both numbers so
    the caller can narrow the request rather than guess.
    """

    error_code = "vcf_result_cap_exceeded"
    audit_status = AuditStatus.DENIED

    def __init__(
        self,
        *,
        cap_name: str,
        cap_value: int,
        requested: int,
        unit: str,
        target_id: TargetId | None = None,
    ) -> None:
        message = (
            f"refused: request needs {requested} {unit} and the cap "
            f"{cap_name} is {cap_value} {unit}. Narrow the request; this "
            f"server refuses rather than returning a truncated series."
        )
        super().__init__(message, target_id=target_id)
        self.cap_name = cap_name
        self.cap_value = cap_value
        self.requested = requested
        self.unit = unit


class TargetConfigurationSuperseded(VcfError):
    """The target was edited while this request was in flight.

    The client for the previous configuration generation is closed. The caller
    must not retry through it: its credentials and its TLS policy are the ones
    the operator just replaced.
    """

    error_code = "vcf_target_configuration_superseded"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        target_id: TargetId | None = None,
        observed_generation: int | None = None,
        current_generation: int | None = None,
    ) -> None:
        super().__init__(message, target_id=target_id)
        self.observed_generation = observed_generation
        self.current_generation = current_generation
