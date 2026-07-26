import unittest

from vcf_ops_mcp.contracts import (
    MUTATING,
    NO_PAYLOAD,
    REGISTRATION_SCHEMA_VERSION,
    REQUIRED_REGISTRATION_CORE,
    TEST_ONLY_MUTATING_CAPABILITY,
    ConfigurationGeneration,
    IdentityDeny,
    InvalidationMode,
    InvalidationResult,
    KeyId,
    RequestIdentity,
    ResponseEnvelope,
    TargetConfigurationChange,
    TargetId,
    TargetPosture,
    TargetRecord,
    TerminalState,
    extract_request_identity,
    invalidation_mode_for_change,
)


class ContractTests(unittest.TestCase):
    def test_production_mutating_set_is_empty(self) -> None:
        self.assertEqual(MUTATING, frozenset())
        self.assertNotIn(TEST_ONLY_MUTATING_CAPABILITY, MUTATING)
        self.assertEqual(
            frozenset({TEST_ONLY_MUTATING_CAPABILITY}),
            frozenset({"test:mutating"}),
        )

    def test_registration_required_core_is_explicit(self) -> None:
        self.assertEqual(REGISTRATION_SCHEMA_VERSION, 1)
        self.assertEqual(
            REQUIRED_REGISTRATION_CORE,
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
            },
        )

    def test_outcome_unknown_is_distinct_and_payload_is_subordinate(self) -> None:
        envelope = ResponseEnvelope(
            state=TerminalState.OUTCOME_UNKNOWN,
            outcome_unknown_payload={"value": 7},
            retryable=False,
        )

        self.assertIs(envelope.success, NO_PAYLOAD)
        self.assertEqual(envelope.outcome_unknown_payload, {"value": 7})
        self.assertNotEqual(envelope.state, TerminalState.OK)
        self.assertNotEqual(envelope.state, TerminalState.ERROR)
        with self.assertRaises(ValueError):
            ResponseEnvelope(
                state=TerminalState.OUTCOME_UNKNOWN,
                success={"value": 7},
                outcome_unknown_payload={"value": 7},
            )
        with self.assertRaises(ValueError):
            ResponseEnvelope(
                state=TerminalState.OUTCOME_UNKNOWN,
                outcome_unknown_payload={"value": 7},
                retryable=True,
            )
        none_payload = ResponseEnvelope(
            state=TerminalState.OUTCOME_UNKNOWN,
            outcome_unknown_payload=None,
        )
        self.assertIsNone(none_payload.outcome_unknown_payload)

    def test_absent_identity_is_an_auditable_typed_deny(self) -> None:
        class Context:
            class RequestContext:
                request = None

            request_context = RequestContext()

        for request in (None, type("Request", (), {"state": object()})()):
            Context.request_context.request = request
            with self.assertRaises(IdentityDeny) as raised:
                extract_request_identity(Context())
            self.assertEqual(raised.exception.audit_status.value, "denied")
            self.assertEqual(
                raised.exception.error_code,
                "request_identity_missing_or_invalid",
            )

        identity = RequestIdentity(
            key_id=KeyId("key-1"),
            granted_scopes=frozenset(),
            allowed_targets=frozenset(),
        )
        Context.request_context.request = type(
            "Request",
            (),
            {"state": type("State", (), {"identity": identity})()},
        )()
        self.assertIs(extract_request_identity(Context()), identity)

    def test_tls_tightening_requires_cancel(self) -> None:
        common = {
            "id": TargetId("target-1"),
            "name": "target",
            "fqdn": "",
            "posture": TargetPosture.READ_ONLY,
            "is_prod": False,
            "auth_source": "local",
        }
        previous = TargetRecord(
            **common,
            verify_ssl=False,
            configuration_generation=ConfigurationGeneration(1),
        )
        tightened = TargetRecord(
            **common,
            verify_ssl=True,
            configuration_generation=ConfigurationGeneration(2),
        )
        ordinary = TargetRecord(
            **common,
            verify_ssl=False,
            configuration_generation=ConfigurationGeneration(2),
        )

        self.assertIs(
            invalidation_mode_for_change(previous, tightened),
            InvalidationMode.CANCEL,
        )
        self.assertIs(
            invalidation_mode_for_change(previous, ordinary),
            InvalidationMode.DRAIN,
        )

    def test_configuration_generation_must_advance(self) -> None:
        change = TargetConfigurationChange(
            target_id=TargetId("target-1"),
            previous_generation=ConfigurationGeneration(4),
            current_generation=ConfigurationGeneration(5),
        )
        self.assertEqual(change.current_generation, 5)

        with self.assertRaises(ValueError):
            TargetConfigurationChange(
                target_id=TargetId("target-1"),
                previous_generation=ConfigurationGeneration(5),
                current_generation=ConfigurationGeneration(5),
            )

    def test_drain_and_cancel_results_are_distinguishable(self) -> None:
        change = TargetConfigurationChange(
            target_id=TargetId("target-1"),
            previous_generation=ConfigurationGeneration(1),
            current_generation=ConfigurationGeneration(2),
        )
        drained = InvalidationResult(
            change=change,
            mode=InvalidationMode.DRAIN,
            drained_requests=2,
            cancelled_requests=0,
        )
        cancelled = InvalidationResult(
            change=change,
            mode=InvalidationMode.CANCEL,
            drained_requests=0,
            cancelled_requests=2,
        )

        self.assertNotEqual(drained.mode, cancelled.mode)
        with self.assertRaises(ValueError):
            InvalidationResult(
                change=change,
                mode=InvalidationMode.DRAIN,
                drained_requests=1,
                cancelled_requests=1,
            )


if __name__ == "__main__":
    unittest.main()
