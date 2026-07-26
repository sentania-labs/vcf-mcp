import asyncio
import unittest
from types import SimpleNamespace

from vcf_ops_mcp.contracts import (
    TEST_ONLY_MUTATING_CAPABILITY,
    Capability,
    ConfigurationGeneration,
    HttpMethod,
    KeyId,
    OutboundContract,
    RequestIdentity,
    TargetId,
    TargetPosture,
    TargetRecord,
    TerminalState,
)
from vcf_ops_mcp.dispatcher import (
    DispatchDependencies,
    DispatchError,
    Dispatcher,
    ToolRegistry,
)
from vcf_ops_mcp.dispatcher.reservations import (
    CALL_RESERVATION_BYTES,
    CHECKPOINT_HEADROOM_BYTES,
    FreeSpaceReservations,
)


class FakeTargets:
    def __init__(self, target: TargetRecord) -> None:
        self.target = target

    async def get(self, target_id: TargetId) -> TargetRecord | None:
        return self.target if target_id == self.target.id else None


class FakeAudit:
    def __init__(self, fail_on_write: int | None = None) -> None:
        self.records = []
        self.fail_on_write = fail_on_write

    async def append_committed(self, record) -> None:
        write_number = len(self.records) + 1
        if write_number == self.fail_on_write:
            raise OSError("synthetic audit failure")
        self.records.append(record)


def context_for(identity: RequestIdentity):
    return SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(
                state=SimpleNamespace(identity=identity),
            )
        )
    )


def target(posture: TargetPosture, *, is_prod: bool = False) -> TargetRecord:
    return TargetRecord(
        id=TargetId("target-1"),
        name="fixture",
        fqdn="fixture.invalid",
        posture=posture,
        is_prod=is_prod,
        verify_ssl=True,
        auth_source="local",
        configuration_generation=ConfigurationGeneration(1),
    )


def registry_with(capability, handler) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        {
            "schema_version": 1,
            "name": "fixture_tool",
            "capability": capability,
            "key_scope": capability,
            "target_policy": "required",
            "argument_digest_policy": "canonical-json-v1",
            "projection": "fixture-v1",
            "outbound_contract": OutboundContract(
                method=HttpMethod.POST,
                path_template="/api/resources/query",
                permitted_query_parameters=frozenset({"page"}),
            ),
            "audited_handler": handler,
            "fixture.note": "additive extension",
        }
    )
    registry.freeze()
    return registry


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_denials_are_audited_with_attribution(self) -> None:
        async def handler(_target, _arguments):
            return {}

        fixtures = (
            ("key_revoked", {"revoked": True}),
            ("target_not_allowed", {"allowed_targets": frozenset()}),
            ("scope_denied", {"granted_scopes": frozenset()}),
            ("scope_denied", {"global_scopes": frozenset()}),
            (
                "target_read_only",
                {
                    "capability": TEST_ONLY_MUTATING_CAPABILITY,
                    "mutating": frozenset({TEST_ONLY_MUTATING_CAPABILITY}),
                },
            ),
        )
        for expected_error, overrides in fixtures:
            with self.subTest(error=expected_error, overrides=overrides):
                audit = FakeAudit()
                capability = overrides.get(
                    "capability", Capability.READ_INVENTORY
                )
                dispatcher, identity = self.make_dispatcher(
                    target(TargetPosture.READ_ONLY),
                    audit,
                    capability,
                    handler,
                    mutating=overrides.get("mutating", frozenset()),
                    global_scopes=overrides.get(
                        "global_scopes", frozenset({capability})
                    ),
                )
                identity = RequestIdentity(
                    key_id=identity.key_id,
                    granted_scopes=overrides.get(
                        "granted_scopes", identity.granted_scopes
                    ),
                    allowed_targets=overrides.get(
                        "allowed_targets", identity.allowed_targets
                    ),
                    revoked=overrides.get("revoked", False),
                )
                with self.assertRaises(DispatchError) as raised:
                    await dispatcher.dispatch(
                        "fixture_tool",
                        context=context_for(identity),
                        target_id=TargetId("target-1"),
                        arguments={},
                        deadline_seconds=1,
                    )
                self.assertEqual(raised.exception.error_code, expected_error)
                self.assertEqual(len(audit.records), 1)
                self.assertEqual(audit.records[0].status.value, "denied")
                self.assertEqual(audit.records[0].key_id, KeyId("key-1"))
                self.assertEqual(audit.records[0].target_id, TargetId("target-1"))
                self.assertEqual(audit.records[0].error_code, expected_error)

    async def test_same_dispatcher_reads_identity_for_each_request(self) -> None:
        audit = FakeAudit()

        async def handler(_target, _arguments):
            return {}

        dispatcher, first_identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            audit,
            Capability.READ_INVENTORY,
            handler,
        )
        second_identity = RequestIdentity(
            key_id=KeyId("key-2"),
            granted_scopes=first_identity.granted_scopes,
            allowed_targets=first_identity.allowed_targets,
        )
        for identity in (first_identity, second_identity):
            await dispatcher.dispatch(
                "fixture_tool",
                context=context_for(identity),
                target_id=TargetId("target-1"),
                arguments={},
                deadline_seconds=1,
            )
        self.assertEqual(
            [record.key_id for record in audit.records],
            [KeyId("key-1"), KeyId("key-1"), KeyId("key-2"), KeyId("key-2")],
        )

    async def test_attempt_is_committed_before_handler(self) -> None:
        audit = FakeAudit()

        async def handler(_target, _arguments):
            self.assertEqual([record.status.value for record in audit.records], ["attempt"])
            return {"ok": True}

        dispatcher, identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            audit,
            Capability.READ_INVENTORY,
            handler,
        )
        result = await dispatcher.dispatch(
            "fixture_tool",
            context=context_for(identity),
            target_id=TargetId("target-1"),
            arguments={"kind": "VM"},
            deadline_seconds=1,
        )

        self.assertIs(result.state, TerminalState.OK)
        self.assertEqual(result.success, {"ok": True})
        self.assertEqual(
            [record.status.value for record in audit.records],
            ["attempt", "ok"],
        )
        self.assertNotIn("VM", audit.records[0].arguments_digest)

    async def test_reservation_is_held_through_terminal_commit(self) -> None:
        audit = FakeAudit()
        capacity = CHECKPOINT_HEADROOM_BYTES + CALL_RESERVATION_BYTES
        reservations = FreeSpaceReservations(lambda: capacity)

        async def handler(_target, _arguments):
            self.assertEqual(
                reservations.reserved_bytes, CALL_RESERVATION_BYTES
            )
            return {}

        dispatcher, identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            audit,
            Capability.READ_INVENTORY,
            handler,
            reservations=reservations,
        )
        await dispatcher.dispatch(
            "fixture_tool",
            context=context_for(identity),
            target_id=TargetId("target-1"),
            arguments={},
            deadline_seconds=1,
        )
        self.assertEqual(reservations.reserved_bytes, 0)

    async def test_cancellation_is_audited_and_releases_reservation(self) -> None:
        audit = FakeAudit()
        capacity = CHECKPOINT_HEADROOM_BYTES + CALL_RESERVATION_BYTES
        reservations = FreeSpaceReservations(lambda: capacity)
        handler_started = asyncio.Event()

        async def handler(_target, _arguments):
            handler_started.set()
            await asyncio.Future()

        dispatcher, identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            audit,
            Capability.READ_INVENTORY,
            handler,
            reservations=reservations,
        )
        dispatch_task = asyncio.create_task(
            dispatcher.dispatch(
                "fixture_tool",
                context=context_for(identity),
                target_id=TargetId("target-1"),
                arguments={},
                deadline_seconds=10,
            )
        )
        await handler_started.wait()
        dispatch_task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await dispatch_task

        self.assertEqual(
            [record.status.value for record in audit.records],
            ["attempt", "cancelled"],
        )
        self.assertEqual(audit.records[-1].error_code, "handler_cancelled")
        self.assertEqual(reservations.reserved_bytes, 0)

    async def test_attempt_write_failure_refuses_without_running_handler(self) -> None:
        ran = False

        async def handler(_target, _arguments):
            nonlocal ran
            ran = True
            return {}

        dispatcher, identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            FakeAudit(fail_on_write=1),
            Capability.READ_INVENTORY,
            handler,
        )
        with self.assertRaises(DispatchError) as raised:
            await dispatcher.dispatch(
                "fixture_tool",
                context=context_for(identity),
                target_id=TargetId("target-1"),
                arguments={},
                deadline_seconds=1,
            )
        self.assertEqual(raised.exception.error_code, "audit_attempt_write_failed")
        self.assertFalse(ran)

    async def test_terminal_write_failure_returns_unknown_with_payload(self) -> None:
        async def handler(_target, _arguments):
            return {"upstream": "result"}

        dispatcher, identity = self.make_dispatcher(
            target(TargetPosture.READ_ONLY),
            FakeAudit(fail_on_write=2),
            Capability.READ_INVENTORY,
            handler,
        )
        result = await dispatcher.dispatch(
            "fixture_tool",
            context=context_for(identity),
            target_id=TargetId("target-1"),
            arguments={},
            deadline_seconds=1,
        )
        self.assertIs(result.state, TerminalState.OUTCOME_UNKNOWN)
        self.assertEqual(result.outcome_unknown_payload, {"upstream": "result"})
        self.assertFalse(result.retryable)

    async def test_mutating_gate_denies_allows_and_denies(self) -> None:
        async def handler(_target, _arguments):
            return {"ran": True}

        cases = (
            (target(TargetPosture.READ_ONLY), "target_read_only"),
            (target(TargetPosture.ACTIONS_ENABLED), None),
            (
                target(TargetPosture.ACTIONS_ENABLED, is_prod=True),
                "prod_actions_forbidden",
            ),
        )
        for fixture, expected_error in cases:
            with self.subTest(posture=fixture.posture, is_prod=fixture.is_prod):
                dispatcher, identity = self.make_dispatcher(
                    fixture,
                    FakeAudit(),
                    TEST_ONLY_MUTATING_CAPABILITY,
                    handler,
                    mutating=frozenset({TEST_ONLY_MUTATING_CAPABILITY}),
                )
                if expected_error is None:
                    result = await dispatcher.dispatch(
                        "fixture_tool",
                        context=context_for(identity),
                        target_id=fixture.id,
                        arguments={},
                        deadline_seconds=1,
                    )
                    self.assertIs(result.state, TerminalState.OK)
                else:
                    with self.assertRaises(DispatchError) as raised:
                        await dispatcher.dispatch(
                            "fixture_tool",
                            context=context_for(identity),
                            target_id=fixture.id,
                            arguments={},
                            deadline_seconds=1,
                        )
                    self.assertEqual(raised.exception.error_code, expected_error)

    def make_dispatcher(
        self,
        fixture,
        audit,
        capability,
        handler,
        *,
        mutating=frozenset(),
        global_scopes=None,
        reservations=None,
    ):
        identity = RequestIdentity(
            key_id=KeyId("key-1"),
            granted_scopes=frozenset({capability}),
            allowed_targets=frozenset({fixture.id}),
        )
        registry = registry_with(capability, handler)
        dependencies = DispatchDependencies(
            targets=FakeTargets(fixture),
            audit=audit,
            global_scopes=(
                frozenset({capability})
                if global_scopes is None
                else global_scopes
            ),
            digest_key=b"synthetic-test-digest-key",
            mutating=mutating,
            reservations=reservations,
        )
        return Dispatcher(registry, dependencies), identity


class RegistryTests(unittest.TestCase):
    def test_required_core_and_extension_rule_are_enforced(self) -> None:
        async def handler(_target, _arguments):
            return {}

        complete = {
            "schema_version": 1,
            "name": "tool",
            "capability": Capability.READ_TARGETS,
            "key_scope": Capability.READ_TARGETS,
            "target_policy": "required",
            "argument_digest_policy": "canonical-json-v1",
            "projection": "v1",
            "outbound_contract": OutboundContract(
                HttpMethod.GET, "/api/resources", frozenset()
            ),
            "audited_handler": handler,
        }
        with self.assertRaisesRegex(ValueError, "required core"):
            ToolRegistry().register(
                {
                    key: value
                    for key, value in complete.items()
                    if key != "projection"
                }
            )
        with self.assertRaisesRegex(ValueError, "family-qualified"):
            ToolRegistry().register({**complete, "sample_cap": 10})
        spec = ToolRegistry().register({**complete, "metrics.sample_cap": 10})
        self.assertEqual(spec.extensions, {"metrics.sample_cap": 10})


if __name__ == "__main__":
    unittest.main()
