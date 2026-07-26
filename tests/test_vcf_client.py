"""Contract tests for the target client.

Tier 2 per SPEC section 11: no network, ``httpx.MockTransport`` over synthetic
responses, exercising the real client. These tests carry four of the pinned
acceptance criteria for the read plane:

- exactly one token acquisition across N concurrent 401s
- no re-authentication on 403
- a per-request retry counter bounding retry at exactly one under mid-session
  credential revocation
- target edit marks the old client closed, with drain and cancel semantics
"""

from __future__ import annotations

import asyncio
import unittest

import httpx

from vcf_ops_mcp.contracts import (
    ConfigurationGeneration,
    HttpMethod,
    InvalidationMode,
    OutboundContract,
    TargetConfigurationChange,
    TargetId,
    TargetPosture,
    TargetRecord,
    invalidation_mode_for_change,
)
from vcf_ops_mcp.vcf.caps import MAX_UPSTREAM_RESPONSE_BYTES
from vcf_ops_mcp.vcf.client import (
    MAX_REAUTHENTICATIONS_PER_REQUEST,
    TOKEN_REFRESH_SKEW_SECONDS,
    TargetClientRegistry,
    TargetCredentials,
    VcfTargetClient,
)
from vcf_ops_mcp.vcf.errors import (
    AuthenticationError,
    PermissionDeniedError,
    ReauthenticationExhausted,
    ResultCapExceeded,
    TargetConfigurationSuperseded,
    UpstreamProtocolError,
    UpstreamStatusError,
    UpstreamTimeoutError,
)
from vcf_ops_mcp.vcf.outbound import OutboundAllowlist, ReadContract


PASSWORD = "synthetic-not-a-real-password"
FAR_FUTURE_MS = 4_102_444_800_000  # 2100-01-01, well past any test clock.

RESOURCES = ReadContract(
    name="test.resources",
    contract=OutboundContract(
        method=HttpMethod.GET,
        path_template="/api/resources",
        permitted_query_parameters=frozenset({"page", "pageSize", "resourceKind"}),
    ),
    projection_version="resource.v1",
)
ALLOWLIST = OutboundAllowlist([RESOURCES])


def target(
    *,
    generation: int = 1,
    verify_ssl: bool = False,
    target_id: str = "t-1",
) -> TargetRecord:
    return TargetRecord(
        id=TargetId(target_id),
        name="devel",
        fqdn="vcf-ops-devel.invalid",
        posture=TargetPosture.READ_ONLY,
        is_prod=False,
        verify_ssl=verify_ssl,
        auth_source="LOCAL",
        configuration_generation=ConfigurationGeneration(generation),
    )


def json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


class CountingStream(httpx.AsyncByteStream):
    """A response body that reports how much of it was actually pulled.

    The pre-fix client buffered the whole body before measuring it, so a test
    that asserts only on the error passes either way. ``emitted`` is what
    separates the two: a streaming reader stops asking for chunks as soon as
    the running count crosses the cap.
    """

    def __init__(self, *, chunk_size: int, chunks: int) -> None:
        self.chunk_size = chunk_size
        self.chunks = chunks
        self.emitted = 0
        self.closed = False

    async def __aiter__(self):
        for _ in range(self.chunks):
            self.emitted += self.chunk_size
            yield b"x" * self.chunk_size

    async def aclose(self) -> None:
        self.closed = True


class Appliance:
    """A synthetic appliance that counts acquires and validates the token."""

    def __init__(
        self,
        *,
        read_status: int = 200,
        revoked: bool = False,
        stall: asyncio.Event | None = None,
    ) -> None:
        self.acquires = 0
        self.reads = 0
        self.releases = 0
        self.read_status = read_status
        self.revoked = revoked
        self.stall = stall
        self.seen_tokens: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token/acquire"):
            self.acquires += 1
            await asyncio.sleep(0)
            return json_response(
                {
                    "token": f"tok-{self.acquires}",
                    "validity": FAR_FUTURE_MS,
                    "expiresAt": "far future",
                    "roles": [],
                }
            )
        if path.endswith("/token/release"):
            self.releases += 1
            return httpx.Response(200, json={})
        self.reads += 1
        presented = request.headers.get("Authorization", "")
        self.seen_tokens.append(presented)
        if self.stall is not None:
            await self.stall.wait()
        if self.revoked:
            # Mid-session revocation: every token, however fresh, is refused.
            return json_response({"message": "invalid token"}, 401)
        if presented != f"OpsToken tok-{self.acquires}":
            return json_response({"message": "invalid token"}, 401)
        if self.read_status != 200:
            return httpx.Response(
                self.read_status,
                text="<html><body>forbidden</body></html>",
                headers={"content-type": "text/html;charset=utf-8"},
            )
        await asyncio.sleep(0)
        return json_response(
            {
                "pageInfo": {"totalCount": 0, "page": 0, "pageSize": 50},
                "resourceList": [],
            }
        )


def build_client(
    appliance: Appliance | None = None,
    *,
    record: TargetRecord | None = None,
    now: float = 1_700_000_000.0,
    generation_source=None,
) -> tuple[VcfTargetClient, Appliance]:
    appliance = appliance or Appliance()
    record = record or target()
    http = httpx.AsyncClient(
        base_url=f"https://{record.fqdn}/suite-api",
        transport=httpx.MockTransport(appliance),
    )
    client = VcfTargetClient(
        target=record,
        credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
        allowlist=ALLOWLIST,
        http_client=http,
        now=lambda: now,
        generation_source=generation_source,
    )
    return client, appliance


class TokenLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_exactly_one_acquisition_across_concurrent_first_calls(self) -> None:
        client, appliance = build_client()
        try:
            await asyncio.gather(*(client.request_read(RESOURCES) for _ in range(8)))
        finally:
            await client.aclose()
        self.assertEqual(appliance.acquires, 1)
        self.assertEqual(client.token_acquisitions, 1)

    async def test_exactly_one_reacquisition_across_concurrent_401s(self) -> None:
        """The pinned criterion: an N-caller 401 storm acquires exactly once."""

        client, appliance = build_client()
        # Prime a token, then invalidate it server-side so every concurrent
        # caller's first read comes back 401 with the same auth generation.
        await client.request_read(RESOURCES)
        self.assertEqual(appliance.acquires, 1)
        appliance.acquires = 0  # every held token is now stale server-side

        try:
            results = await asyncio.gather(
                *(client.request_read(RESOURCES) for _ in range(8))
            )
        finally:
            await client.aclose()

        self.assertEqual(len(results), 8)
        # One acquire for the storm, not eight. The first arrival under the
        # lock still matches the auth generation it captured; the rest find it
        # moved and take the winner's token.
        self.assertEqual(appliance.acquires, 1)
        self.assertEqual(client.token_acquisitions, 2)

    async def test_no_reauthentication_on_403(self) -> None:
        client, appliance = build_client(Appliance(read_status=403))
        try:
            with self.assertRaises(PermissionDeniedError) as caught:
                await client.request_read(RESOURCES)
        finally:
            await client.aclose()
        self.assertEqual(appliance.acquires, 1)
        self.assertEqual(appliance.reads, 1)
        self.assertEqual(caught.exception.error_code, "vcf_permission_denied")
        self.assertEqual(caught.exception.path, "/api/resources")

    async def test_retry_is_bounded_at_one_under_revocation(self) -> None:
        """Decision 4 (4B): the bound is a per-request counter, not the generation."""

        client, appliance = build_client(Appliance(revoked=True))
        try:
            with self.assertRaises(ReauthenticationExhausted):
                await client.request_read(RESOURCES)
        finally:
            await client.aclose()
        self.assertEqual(MAX_REAUTHENTICATIONS_PER_REQUEST, 1)
        self.assertEqual(appliance.reads, 2)
        self.assertEqual(client.token_acquisitions, 2)

    async def test_concurrent_revoked_callers_each_stop_after_one_retry(self) -> None:
        """The generation keeps moving under revocation; the counter still binds."""

        client, appliance = build_client(Appliance(revoked=True))
        try:
            outcomes = await asyncio.gather(
                *(client.request_read(RESOURCES) for _ in range(5)),
                return_exceptions=True,
            )
        finally:
            await client.aclose()
        self.assertTrue(
            all(isinstance(o, ReauthenticationExhausted) for o in outcomes), outcomes
        )
        # Five callers, two reads each, and never an unbounded acquire loop.
        self.assertEqual(appliance.reads, 10)
        self.assertLessEqual(client.token_acquisitions, 6)

    async def test_token_is_reused_until_the_refresh_skew(self) -> None:
        clock = {"now": 1_700_000_000.0}
        appliance = Appliance()
        record = target()
        http = httpx.AsyncClient(
            base_url=f"https://{record.fqdn}/suite-api",
            transport=httpx.MockTransport(appliance),
        )
        expiry = FAR_FUTURE_MS / 1000.0
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=http,
            now=lambda: clock["now"],
        )
        try:
            await client.request_read(RESOURCES)
            clock["now"] = expiry - TOKEN_REFRESH_SKEW_SECONDS - 1
            await client.request_read(RESOURCES)
            self.assertEqual(appliance.acquires, 1)
            clock["now"] = expiry - TOKEN_REFRESH_SKEW_SECONDS + 1
            await client.request_read(RESOURCES)
        finally:
            await client.aclose()
        self.assertEqual(appliance.acquires, 2)

    async def test_release_is_best_effort_and_never_raises(self) -> None:
        async def failing(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/acquire"):
                return json_response({"token": "tok-1", "validity": FAR_FUTURE_MS})
            if request.url.path.endswith("/token/release"):
                raise httpx.ConnectError("appliance went away")
            return json_response(
                {"pageInfo": {"totalCount": 0, "page": 0, "pageSize": 50}, "resourceList": []}
            )

        record = target()
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(failing),
            ),
        )
        await client.request_read(RESOURCES)
        await client.aclose()  # must not raise


class ErrorDecodingTests(unittest.IsolatedAsyncioTestCase):
    async def test_html_body_on_success_status_is_a_protocol_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/acquire"):
                return json_response({"token": "tok-1", "validity": FAR_FUTURE_MS})
            return httpx.Response(
                200, text="<html>hello</html>", headers={"content-type": "text/html"}
            )

        record = target()
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(handler),
            ),
        )
        with self.assertRaises(UpstreamProtocolError):
            await client.request_read(RESOURCES)
        await client.aclose(release_token=False)

    async def test_timeout_is_typed_and_retryable(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/acquire"):
                return json_response({"token": "tok-1", "validity": FAR_FUTURE_MS})
            raise httpx.ReadTimeout("too slow", request=request)

        record = target()
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(handler),
            ),
        )
        with self.assertRaises(UpstreamTimeoutError) as caught:
            await client.request_read(RESOURCES)
        self.assertTrue(caught.exception.retryable)
        await client.aclose(release_token=False)

    async def test_oversize_response_is_refused_by_the_cap(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/acquire"):
                return json_response({"token": "tok-1", "validity": FAR_FUTURE_MS})
            return httpx.Response(
                200,
                content=b'{"filler":"' + b"x" * (9 * 1024 * 1024) + b'"}',
                headers={"content-type": "application/json"},
            )

        record = target()
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(handler),
            ),
        )
        with self.assertRaises(ResultCapExceeded) as caught:
            await client.request_read(RESOURCES)
        self.assertIn("MAX_UPSTREAM_RESPONSE_BYTES", str(caught.exception))
        await client.aclose(release_token=False)

    async def test_oversize_response_is_aborted_before_it_is_buffered(self) -> None:
        """The cap has to bite while streaming, not after the allocation.

        Asserting only on the raised error is not enough: a client that
        buffers the whole body and then measures it raises the same error
        having already spent the memory. So the assertion here is on the
        stream itself, which records how many bytes it was asked for.
        """

        chunk_size = 64 * 1024
        stream = CountingStream(chunk_size=chunk_size, chunks=160)  # 10 MiB

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/acquire"):
                return json_response({"token": "tok-1", "validity": FAR_FUTURE_MS})
            return httpx.Response(
                200,
                stream=stream,
                headers={"content-type": "application/json"},
            )

        record = target()
        client = VcfTargetClient(
            target=record,
            credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(handler),
            ),
        )
        with self.assertRaises(ResultCapExceeded) as caught:
            await client.request_read(RESOURCES)
        self.assertIn("MAX_UPSTREAM_RESPONSE_BYTES", str(caught.exception))
        # Peak accumulation is the cap plus at most the chunk that crossed it.
        self.assertLessEqual(stream.emitted, MAX_UPSTREAM_RESPONSE_BYTES + chunk_size)
        self.assertGreater(stream.emitted, MAX_UPSTREAM_RESPONSE_BYTES)
        self.assertTrue(stream.closed)
        await client.aclose(release_token=False)

    async def test_upstream_500_is_a_status_error(self) -> None:
        client, _ = build_client(Appliance(read_status=500))
        with self.assertRaises(UpstreamStatusError) as caught:
            await client.request_read(RESOURCES)
        self.assertEqual(caught.exception.status_code, 500)
        await client.aclose(release_token=False)

    async def test_no_secret_material_reaches_error_text_or_repr(self) -> None:
        async def refusing(request: httpx.Request) -> httpx.Response:
            return json_response({"message": "invalid credentials"}, 401)

        record = target()
        credentials = TargetCredentials("svc-reader", PASSWORD, "LOCAL")
        client = VcfTargetClient(
            target=record,
            credentials=credentials,
            allowlist=ALLOWLIST,
            http_client=httpx.AsyncClient(
                base_url=f"https://{record.fqdn}/suite-api",
                transport=httpx.MockTransport(refusing),
            ),
        )
        with self.assertRaises(AuthenticationError) as caught:
            await client.request_read(RESOURCES)
        rendered = f"{caught.exception!r} {caught.exception} {credentials!r} {credentials}"
        self.assertNotIn(PASSWORD, rendered)
        self.assertNotIn("svc-reader", rendered)
        await client.aclose(release_token=False)


class InvalidationTests(unittest.IsolatedAsyncioTestCase):
    def registry(self, appliance: Appliance) -> TargetClientRegistry:
        def factory(record: TargetRecord) -> VcfTargetClient:
            return VcfTargetClient(
                target=record,
                credentials=TargetCredentials("svc-reader", PASSWORD, "LOCAL"),
                allowlist=ALLOWLIST,
                http_client=httpx.AsyncClient(
                    base_url=f"https://{record.fqdn}/suite-api",
                    transport=httpx.MockTransport(appliance),
                ),
            )

        return TargetClientRegistry(client_factory=factory)

    async def test_drain_lets_started_work_finish_and_refuses_new_work(self) -> None:
        stall = asyncio.Event()
        appliance = Appliance(stall=stall)
        registry = self.registry(appliance)
        record = target(generation=1)
        client = registry.get(record)

        started = asyncio.create_task(client.request_read(RESOURCES))
        await asyncio.sleep(0)
        while appliance.reads == 0:
            await asyncio.sleep(0)

        change = TargetConfigurationChange(
            target_id=record.id,
            previous_generation=ConfigurationGeneration(1),
            current_generation=ConfigurationGeneration(2),
        )
        invalidation = asyncio.create_task(
            registry.invalidate(change, mode=InvalidationMode.DRAIN)
        )
        await asyncio.sleep(0)

        self.assertTrue(client.is_closed)
        with self.assertRaises(TargetConfigurationSuperseded):
            await client.request_read(RESOURCES)

        stall.set()
        result = await invalidation

        # DRAIN lets the started request finish its transfer and then refuses
        # its result as superseded, retryably. That is contracts.py's rule: a
        # generation mismatch discards the old result. What DRAIN buys is the
        # orderly unwind and the typed error, not a stale body.
        with self.assertRaises(TargetConfigurationSuperseded) as drained:
            await started
        self.assertTrue(drained.exception.retryable)

        self.assertEqual(result.mode, InvalidationMode.DRAIN)
        self.assertEqual(result.drained_requests, 1)
        self.assertEqual(result.cancelled_requests, 0)

        # A later lookup lazily creates a client only for the new generation.
        replacement = registry.get(target(generation=2))
        self.assertIsNot(replacement, client)
        self.assertEqual(int(replacement.configuration_generation), 2)
        await registry.aclose_all()

    async def test_cancel_unwinds_started_work(self) -> None:
        stall = asyncio.Event()
        appliance = Appliance(stall=stall)
        registry = self.registry(appliance)
        record = target(generation=1, verify_ssl=False)
        client = registry.get(record)

        started = asyncio.create_task(client.request_read(RESOURCES))
        while appliance.reads == 0:
            await asyncio.sleep(0)

        change = TargetConfigurationChange(
            target_id=record.id,
            previous_generation=ConfigurationGeneration(1),
            current_generation=ConfigurationGeneration(2),
        )
        result = await registry.invalidate(change, mode=InvalidationMode.CANCEL)

        self.assertEqual(result.cancelled_requests, 1)
        self.assertEqual(result.drained_requests, 0)
        with self.assertRaises(asyncio.CancelledError):
            await started
        await registry.aclose_all()

    async def test_tightening_tls_verification_selects_cancel(self) -> None:
        """contracts.invalidation_mode_for_change is the mode selector."""

        previous = target(generation=1, verify_ssl=False)
        current = target(generation=2, verify_ssl=True)
        self.assertIs(
            invalidation_mode_for_change(previous, current), InvalidationMode.CANCEL
        )
        self.assertIs(
            invalidation_mode_for_change(current, target(generation=3, verify_ssl=True)),
            InvalidationMode.DRAIN,
        )

    async def test_a_generation_move_discards_an_in_flight_result(self) -> None:
        """The result of a read fetched with superseded configuration is refused."""

        generation = {"value": ConfigurationGeneration(1)}
        client, appliance = build_client(
            generation_source=lambda: generation["value"],
        )
        original_handler = appliance.__call__

        async def moving(request: httpx.Request) -> httpx.Response:
            response = await original_handler(request)
            if not request.url.path.endswith("acquire"):
                generation["value"] = ConfigurationGeneration(2)
            return response

        client._http = httpx.AsyncClient(  # noqa: SLF001, rebinding the mock transport
            base_url="https://vcf-ops-devel.invalid/suite-api",
            transport=httpx.MockTransport(moving),
        )
        with self.assertRaises(TargetConfigurationSuperseded) as caught:
            await client.request_read(RESOURCES)
        self.assertEqual(caught.exception.observed_generation, 1)
        self.assertEqual(caught.exception.current_generation, 2)
        await client.aclose(release_token=False)

    async def test_registry_refuses_a_lookup_for_a_stale_generation(self) -> None:
        registry = self.registry(Appliance())
        registry.get(target(generation=1))
        with self.assertRaises(TargetConfigurationSuperseded):
            registry.get(target(generation=2))
        await registry.aclose_all()

    async def test_invalidating_an_unknown_target_is_a_no_op(self) -> None:
        registry = self.registry(Appliance())
        change = TargetConfigurationChange(
            target_id=TargetId("absent"),
            previous_generation=ConfigurationGeneration(1),
            current_generation=ConfigurationGeneration(2),
        )
        result = await registry.invalidate(change, mode=InvalidationMode.DRAIN)
        self.assertEqual(result.drained_requests, 0)
        self.assertEqual(result.cancelled_requests, 0)


if __name__ == "__main__":
    unittest.main()
