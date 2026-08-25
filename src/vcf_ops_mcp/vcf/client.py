"""One VCF Ops client per registered target.

SPEC section 7. This module owns the ``/suite-api`` base URL, the session
token, the per-target TLS policy, and the only outbound path tool code has.

Measured behaviors this implementation is built on, all against
``vcf-lab-operations-devel.int.sentania.net``:

- The canonical auth header is ``Authorization: OpsToken <token>`` (record
  006). ``vRealizeOpsToken`` also answers 200 and is recorded here as a comment
  only. ``Bearer`` is a 401.
- ``POST /api/auth/token/acquire`` returns ``token``, ``validity`` (an absolute
  epoch-milliseconds expiry), ``expiresAt`` (a human string), and ``roles``
  (always empty, never usable for authorization). Measured TTL is 6.0 hours.
- ``authSource`` for a local user is ``LOCAL`` (or omitted entirely). The
  string ``Local Users``, which is what the UI calls it, is a 401. A wrong auth
  source and a wrong password are byte-identical 401s, so no error message here
  claims to know which one happened.
- Repeated acquires return distinct tokens and old tokens stay valid, so a
  re-auth storm is wasteful rather than dangerous. It is still bounded to
  exactly one re-acquisition here.
- ``POST /api/events/query`` answers 403 with an HTML body for a ReadOnly
  role, so 403 never triggers re-authentication and body decoding never
  assumes JSON.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import Callable, Mapping

import httpx

from vcf_ops_mcp.contracts import (
    ConfigurationGeneration,
    HttpMethod,
    InvalidationMode,
    InvalidationResult,
    JsonObject,
    TargetConfigurationChange,
    TargetId,
    TargetRecord,
)
from vcf_ops_mcp.vcf.caps import enforce_response_size
from vcf_ops_mcp.vcf.errors import (
    AuthenticationError,
    PermissionDeniedError,
    ReauthenticationExhausted,
    TargetConfigurationSuperseded,
    TlsVerificationError,
    UpstreamProtocolError,
    UpstreamStatusError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from vcf_ops_mcp.vcf.outbound import (
    OutboundAllowlist,
    ReadContract,
    check_body,
    check_query,
    render_path,
)


SUITE_API_ROOT = "/suite-api"
TOKEN_ACQUIRE_PATH = "/api/auth/token/acquire"
TOKEN_RELEASE_PATH = "/api/auth/token/release"

# Refresh margin against the measured 6.0 hour TTL.
TOKEN_REFRESH_SKEW_SECONDS = 300.0
DEFAULT_TOKEN_TTL_SECONDS = 6 * 60 * 60.0

# Decision 4 (4B). Retry is bounded by a counter on the request, not by the
# auth generation. Under mid-session credential revocation the generation keeps
# moving for reasons unrelated to this request, so a caller can keep finding a
# "fresh" token that also 401s. One is the whole budget; the second 401 is a
# typed terminal error.
MAX_REAUTHENTICATIONS_PER_REQUEST = 1

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
TOKEN_RELEASE_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)

_JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def build_tls_verifier(
    target: TargetRecord, root_ca_pem: str | None
) -> bool | ssl.SSLContext:
    """Build one target's TLS policy without changing process-wide trust."""

    if not target.verify_ssl:
        return False
    if root_ca_pem is None:
        return True
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=root_ca_pem)
    return context


class TargetCredentials:
    """Credential material for one target. Never logged, never repr'd."""

    __slots__ = ("_username", "_password", "auth_source")

    def __init__(
        self, username: str, password: str, auth_source: str | None = None
    ) -> None:
        self._username = username
        self._password = password
        # None or "LOCAL" both authenticate a local user. The admin picker's
        # "Local users" entry must send "LOCAL", not its own label.
        self.auth_source = auth_source

    def __repr__(self) -> str:
        return "<TargetCredentials redacted>"

    __str__ = __repr__

    def acquire_payload(self) -> dict[str, str]:
        payload = {"username": self._username, "password": self._password}
        if self.auth_source:
            payload["authSource"] = self.auth_source
        return payload

    def basic_auth_tuple(self) -> tuple[str, str]:
        """Return credentials only to an internal auth implementation."""

        return self._username, self._password


class _Token:
    """A held session token. Its value never reaches a repr or a log field."""

    __slots__ = ("value", "expires_at", "generation")

    def __init__(self, value: str, expires_at: float, generation: int) -> None:
        self.value = value
        self.expires_at = expires_at
        self.generation = generation

    def __repr__(self) -> str:
        return f"<_Token generation={self.generation} redacted>"

    __str__ = __repr__


class VcfTargetClient:
    """The single outbound path for one registered target.

    Only ``request_read`` exists. A ``request_mutation`` counterpart is Phase 2
    work and is deliberately absent rather than present and disabled: there is
    nothing here for a mistaken call to reach.
    """

    def __init__(
        self,
        *,
        target: TargetRecord,
        credentials: TargetCredentials,
        allowlist: OutboundAllowlist,
        http_client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
        generation_source: Callable[[], ConfigurationGeneration | None] | None = None,
        root_ca_pem: str | None = None,
    ) -> None:
        self._target = target
        self._credentials = credentials
        self._allowlist = allowlist
        self._now = now
        self._generation_source = generation_source
        self._http = http_client or httpx.AsyncClient(
            base_url=f"https://{target.fqdn}{SUITE_API_ROOT}",
            verify=build_tls_verifier(target, root_ca_pem),
            timeout=DEFAULT_TIMEOUT,
        )
        self._auth_lock = asyncio.Lock()
        self._token: _Token | None = None
        self._auth_generation = 0
        self._acquisitions = 0
        self._closed = False
        self._inflight: dict[asyncio.Task[object], int] = {}
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def target_id(self) -> TargetId:
        return self._target.id

    @property
    def configuration_generation(self) -> ConfigurationGeneration:
        return self._target.configuration_generation

    @property
    def token_acquisitions(self) -> int:
        """How many times a token was acquired. Asserted by the auth tests."""

        return self._acquisitions

    @property
    def auth_generation(self) -> int:
        return self._auth_generation

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def inflight_requests(self) -> int:
        return sum(self._inflight.values())

    async def request_read(
        self,
        contract: ReadContract,
        *,
        path_parameters: Mapping[str, str] | None = None,
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> JsonObject:
        """Issue one allowlisted read and return its decoded JSON object."""

        self._allowlist.check(contract)
        path = render_path(contract, path_parameters)
        params = check_query(contract, query)
        payload = check_body(contract, body)
        self._refuse_if_superseded(self._target.configuration_generation)

        observed_generation = self._target.configuration_generation
        reauthentications = 0
        task = asyncio.current_task()
        self._enter(task)
        try:
            while True:
                token, seen_auth_generation = await self._session_token()
                response = await self._send(
                    contract.contract.method, path, params, payload, token
                )
                if response.status_code == 401:
                    if reauthentications >= MAX_REAUTHENTICATIONS_PER_REQUEST:
                        raise ReauthenticationExhausted(
                            "a freshly acquired token was refused with 401; "
                            "the credential was most likely revoked mid-session",
                            target_id=self._target.id,
                        )
                    reauthentications += 1
                    self._refuse_if_superseded(observed_generation)
                    await self._reacquire(seen_auth_generation)
                    continue
                if response.status_code == 403:
                    # Never re-authenticate here. The credential is valid.
                    raise PermissionDeniedError(
                        "the target refused this read for the credential's role",
                        target_id=self._target.id,
                        path=path,
                    )
                if response.status_code >= 400:
                    raise UpstreamStatusError(
                        f"the target answered {response.status_code} for this read",
                        status_code=response.status_code,
                        target_id=self._target.id,
                        path=path,
                    )
                decoded = self._decode(response, path)
                self._refuse_if_superseded(observed_generation)
                return decoded
        finally:
            self._exit(task)

    async def _session_token(self) -> tuple[str, int]:
        """Return a live token, acquiring at most once across concurrent callers."""

        token = self._token
        if token is not None and not self._is_stale(token):
            return token.value, token.generation
        async with self._auth_lock:
            token = self._token
            if token is not None and not self._is_stale(token):
                return token.value, token.generation
            acquired = await self._acquire_locked()
            return acquired.value, acquired.generation

    async def _reacquire(self, seen_generation: int) -> tuple[str, int]:
        """Re-acquire after a 401, exactly once across an N-caller storm.

        Each caller captured the auth generation before it issued its request.
        Under the lock, only the first arrival still matches; the others find
        the generation moved and take the winner's token without acquiring.
        """

        async with self._auth_lock:
            current = self._token
            if current is not None and current.generation != seen_generation:
                return current.value, current.generation
            acquired = await self._acquire_locked()
            return acquired.value, acquired.generation

    async def _acquire_locked(self) -> _Token:
        try:
            response = await self._http.post(
                TOKEN_ACQUIRE_PATH,
                json=self._credentials.acquire_payload(),
                headers=_JSON_HEADERS,
            )
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, TOKEN_ACQUIRE_PATH) from None
        self._acquisitions += 1
        if response.status_code == 401:
            raise AuthenticationError(
                "the target refused these credentials; a wrong password and a "
                "wrong auth source are indistinguishable on this API",
                target_id=self._target.id,
            )
        if response.status_code >= 400:
            raise UpstreamStatusError(
                f"token acquisition answered {response.status_code}",
                status_code=response.status_code,
                target_id=self._target.id,
                path=TOKEN_ACQUIRE_PATH,
            )
        body = self._decode(response, TOKEN_ACQUIRE_PATH)
        value = body.get("token")
        if not isinstance(value, str) or not value:
            raise UpstreamProtocolError(
                "token acquisition returned no token field",
                target_id=self._target.id,
            )
        validity = body.get("validity")
        if isinstance(validity, int) and validity > 0:
            # validity is an absolute epoch in milliseconds, not a duration.
            expires_at = validity / 1000.0
        else:
            expires_at = self._now() + DEFAULT_TOKEN_TTL_SECONDS
        self._auth_generation += 1
        token = _Token(value, expires_at, self._auth_generation)
        self._token = token
        return token

    def _is_stale(self, token: _Token) -> bool:
        return self._now() >= token.expires_at - TOKEN_REFRESH_SKEW_SECONDS

    async def _send(
        self,
        method: HttpMethod,
        path: str,
        params: Mapping[str, object],
        body: Mapping[str, object] | None,
        token: str,
    ) -> httpx.Response:
        headers = dict(_JSON_HEADERS)
        # Record 006 selects OpsToken. vRealizeOpsToken is an accepted alias on
        # 9.0.2 and is not sent.
        headers["Authorization"] = f"OpsToken {token}"
        try:
            request = self._http.build_request(
                str(method),
                path,
                params=params or None,
                json=body,
                headers=headers,
            )
            # Streamed, not buffered. A buffering send allocates the whole body
            # before any cap can look at it, which makes MAX_UPSTREAM_RESPONSE_
            # BYTES advisory rather than load bearing.
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, path) from None
        try:
            content = await self._read_capped(response, path)
        finally:
            await response.aclose()
        # Hand the rest of the client an ordinary buffered response over the
        # bytes we accepted, so decoding, status handling, and retry are
        # unchanged.
        return httpx.Response(
            status_code=response.status_code,
            headers=_rebuffered_headers(response.headers),
            content=content,
            request=request,
        )

    async def _read_capped(self, response: httpx.Response, path: str) -> bytes:
        """Accumulate a streamed body, aborting the moment it passes the cap.

        The check runs per chunk, so peak accumulation is the cap plus one
        chunk rather than whatever the target chose to send. ``aiter_bytes``
        yields decoded bytes, so a compressed bomb is measured at its expanded
        size, which is the size that matters here.
        """

        buffered = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                buffered.extend(chunk)
                enforce_response_size(
                    byte_count=len(buffered), target_id=self._target.id
                )
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, path) from None
        return bytes(buffered)

    def _transport_error(self, exc: httpx.HTTPError, path: str) -> Exception:
        if isinstance(exc, httpx.TimeoutException):
            return UpstreamTimeoutError(
                f"the target did not answer within the configured timeout "
                f"({type(exc).__name__})",
                target_id=self._target.id,
            )
        if _is_certificate_failure(exc):
            return TlsVerificationError(
                "the target's certificate failed verification for this "
                "target's TLS policy",
                target_id=self._target.id,
            )
        return UpstreamUnavailableError(
            f"the target could not be reached ({type(exc).__name__})",
            target_id=self._target.id,
        )

    def _decode(self, response: httpx.Response, path: str) -> JsonObject:
        """Decode a JSON object body, never assuming the body is JSON.

        An invalid token yields JSON and a bad auth scheme yields HTML on this
        appliance, so the content type is checked and the body is never placed
        in the error.
        """

        enforce_response_size(
            byte_count=len(response.content), target_id=self._target.id
        )
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise UpstreamProtocolError(
                f"expected a JSON body and the target sent "
                f"{content_type or 'no content type'}",
                target_id=self._target.id,
            )
        try:
            decoded = response.json()
        except ValueError:
            raise UpstreamProtocolError(
                "the target's response was not decodable JSON",
                target_id=self._target.id,
            ) from None
        if not isinstance(decoded, dict):
            raise UpstreamProtocolError(
                f"expected a JSON object and the target sent a "
                f"{type(decoded).__name__}",
                target_id=self._target.id,
            )
        return decoded

    def _refuse_if_superseded(self, observed: ConfigurationGeneration) -> None:
        """Guard checked before retry and before returning a result."""

        current = (
            self._generation_source()
            if self._generation_source is not None
            else self._target.configuration_generation
        )
        if self._closed or (current is not None and current != observed):
            raise TargetConfigurationSuperseded(
                "this target was edited while the request was in flight; the "
                "client for the previous configuration generation is closed",
                target_id=self._target.id,
                observed_generation=int(observed),
                current_generation=None if current is None else int(current),
            )

    def _enter(self, task: asyncio.Task[object] | None) -> None:
        if task is None:
            return
        self._inflight[task] = self._inflight.get(task, 0) + 1
        self._idle.clear()

    def _exit(self, task: asyncio.Task[object] | None) -> None:
        if task is None:
            return
        remaining = self._inflight.get(task, 0) - 1
        if remaining > 0:
            self._inflight[task] = remaining
        else:
            self._inflight.pop(task, None)
        if not self._inflight:
            self._idle.set()

    def mark_closed(self) -> int:
        """Refuse new work and report how many requests are still in flight.

        Marking is synchronous and happens before any awaiting, so no request
        can enter between the decision to invalidate and the barrier.
        """

        self._closed = True
        return self.inflight_requests

    async def drain(self) -> None:
        """Wait for in-flight work on this closed client to finish."""

        self._assert_not_reentrant()
        await self._idle.wait()

    async def cancel(self) -> int:
        """Cancel in-flight work on this closed client and await it."""

        self._assert_not_reentrant()
        tasks = list(self._inflight)
        for task in tasks:
            task.cancel()
        await self._idle.wait()
        return len(tasks)

    def _assert_not_reentrant(self) -> None:
        if asyncio.current_task() in self._inflight:
            raise RuntimeError(
                "invalidation cannot be awaited from a task that holds an "
                "in-flight request on the client being invalidated"
            )

    async def aclose(self, *, release_token: bool = True) -> None:
        """Release the token best effort, then close the transport.

        Release is best effort and never blocks shutdown: the measured API
        keeps sibling tokens valid, so a missed release costs nothing but a
        server-side entry that expires on its own.
        """

        token = self._token
        if release_token and token is not None:
            try:
                await self._http.post(
                    TOKEN_RELEASE_PATH,
                    headers={
                        **_JSON_HEADERS,
                        "Authorization": f"OpsToken {token.value}",
                    },
                    timeout=TOKEN_RELEASE_TIMEOUT,
                )
            except (httpx.HTTPError, asyncio.CancelledError):
                pass
        self._token = None
        await self._http.aclose()


def _rebuffered_headers(headers: httpx.Headers) -> httpx.Headers:
    """Headers for a response rebuilt from already-decoded bytes.

    ``content-length`` and ``content-encoding`` described the wire body, not
    the bytes we now hold, so they are dropped rather than carried forward as
    claims that are no longer true.
    """

    rebuilt = httpx.Headers(headers)
    rebuilt.pop("content-length", None)
    rebuilt.pop("content-encoding", None)
    return rebuilt


def _is_certificate_failure(exc: httpx.HTTPError) -> bool:
    seen: object = exc
    for _ in range(5):
        text = str(seen)
        if "CERTIFICATE_VERIFY_FAILED" in text or "SSLCertVerificationError" in text:
            return True
        cause = getattr(seen, "__cause__", None) or getattr(seen, "__context__", None)
        if cause is None:
            return False
        seen = cause
    return False


class TargetClientRegistry:
    """Process-level registry of one live client per registered target.

    Implements ``contracts.TargetClientInvalidator``. The admin edit flow calls
    ``invalidate`` after ``TargetRepository.save`` and before reporting
    success.

    Drain-or-cancel semantics, which are the client half of the
    target-configuration-generation protocol:

    - On entry, the client for ``previous_generation`` is marked closed
      synchronously, so it accepts no new work from that instant.
    - ``DRAIN`` lets already-started requests run to completion, then refuses
      their results with ``TargetConfigurationSuperseded``, which is
      retryable. This is ``contracts.py``'s stated obligation: a generation
      mismatch discards the old result and never retries through the closed
      client. What DRAIN buys over CANCEL is an orderly unwind and a typed,
      retryable error for the caller instead of a ``CancelledError``, plus a
      transport that is closed with no request mid-flight on it.
    - ``CANCEL`` cancels those requests where they stand and awaits their
      unwinding. It is selected by
      ``contracts.invalidation_mode_for_change`` when an edit tightens TLS
      verification, because letting a request continue over an unverified
      connection after the operator turned verification on is exactly the
      security action the operator just took away. There, not even finishing
      the transfer is acceptable.
    - Either way the closed client is removed and its transport closed, and a
      later lookup lazily creates a client only for ``current_generation``.

    A caller that receives ``TargetConfigurationSuperseded`` re-reads the
    target and re-issues against the new client. It never sees a body that was
    fetched with credentials or a TLS policy the operator has replaced.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[TargetRecord], VcfTargetClient],
    ) -> None:
        self._client_factory = client_factory
        self._clients: dict[TargetId, VcfTargetClient] = {}

    def get(self, target: TargetRecord) -> VcfTargetClient:
        """Return the live client for this target record, creating it lazily."""

        existing = self._clients.get(target.id)
        if existing is not None:
            if existing.configuration_generation != target.configuration_generation:
                raise TargetConfigurationSuperseded(
                    "the registry holds a client for a different configuration "
                    "generation; the edit's invalidation barrier has not "
                    "completed",
                    target_id=target.id,
                    observed_generation=int(target.configuration_generation),
                    current_generation=int(existing.configuration_generation),
                )
            if existing.is_closed:
                raise TargetConfigurationSuperseded(
                    "the client for this generation is closed",
                    target_id=target.id,
                )
            return existing
        client = self._client_factory(target)
        self._clients[target.id] = client
        return client

    async def invalidate(
        self,
        change: TargetConfigurationChange,
        *,
        mode: InvalidationMode,
    ) -> InvalidationResult:
        client = self._clients.get(change.target_id)
        if client is None:
            return InvalidationResult(
                change=change,
                mode=mode,
                drained_requests=0,
                cancelled_requests=0,
            )
        if client.configuration_generation != change.previous_generation:
            raise TargetConfigurationSuperseded(
                "the live client is not the one this change supersedes",
                target_id=change.target_id,
                observed_generation=int(change.previous_generation),
                current_generation=int(client.configuration_generation),
            )
        inflight = client.mark_closed()
        drained = 0
        cancelled = 0
        if mode is InvalidationMode.DRAIN:
            await client.drain()
            drained = inflight
        else:
            cancelled = await client.cancel()
        self._clients.pop(change.target_id, None)
        await client.aclose()
        return InvalidationResult(
            change=change,
            mode=mode,
            drained_requests=drained,
            cancelled_requests=cancelled,
        )

    async def aclose_all(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            client.mark_closed()
            await client.aclose()
