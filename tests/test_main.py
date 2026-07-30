"""Composition-root and health-gate tests.

These are the first-light tests: they assert that the production entry point
builds an application whose /healthz answers 200 against a real audit store,
and that every way of failing to reach that store answers 503 instead.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from vcf_ops_mcp.app import create_app
from vcf_ops_mcp.audit import AuditStorageUnavailable, SqliteAuditRepository
from vcf_ops_mcp.contracts import (
    AuditRecord,
    AuditStatus,
    CorrelationId,
    KeyId,
    TargetId,
)
from vcf_ops_mcp.main import create_production_app


SECRET_ENVIRONMENT = {"SESSION_SECRET": "test-secret-not-a-real-value"}


def attempt(correlation_id: str) -> AuditRecord:
    return AuditRecord(
        correlation_id=CorrelationId(correlation_id),
        key_id=KeyId("key-1"),
        target_id=TargetId("target-1"),
        tool_name="list_resources",
        arguments_digest="sha256:" + "0" * 64,
        status=AuditStatus.ATTEMPT,
        timestamp=datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC),
    )


class ProductionAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def environment(self, **extra: str) -> dict[str, str]:
        return {
            **SECRET_ENVIRONMENT,
            "AUDIT_DB_PATH": str(self.root / "audit" / "audit.sqlite3"),
            **extra,
        }

    def test_healthz_is_200_through_the_production_entry_point(self) -> None:
        with mock.patch.dict(os.environ, self.environment(), clear=False):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ready"], True)
        self.assertIs(body["audit_writable"], True)
        self.assertEqual(body["unreconciled_outcome_unknown_count"], 0)

    def test_the_entry_point_creates_the_audit_database(self) -> None:
        path = self.root / "audit" / "audit.sqlite3"
        with mock.patch.dict(os.environ, self.environment(), clear=False):
            create_production_app()
        self.assertTrue(path.exists())

    def test_boot_reconciles_attempts_left_open_by_a_prior_process(
        self,
    ) -> None:
        path = self.root / "audit" / "audit.sqlite3"
        crashed = SqliteAuditRepository(path)
        crashed.open()
        asyncio.run(crashed.append_committed(attempt("in-flight")))
        crashed.close()

        with mock.patch.dict(os.environ, self.environment(), clear=False):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        # Reconciliation closed the open attempt, so nothing is left dangling.
        self.assertEqual(response.json()["unreconciled_outcome_unknown_count"], 0)

    def test_an_unopenable_store_boots_degraded_and_answers_503(self) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        environment = self.environment(
            AUDIT_DB_PATH=str(blocker / "audit.sqlite3")
        )
        with mock.patch.dict(os.environ, environment, clear=False):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")
        # Degraded, not crash-looping: the process is up and says why it is
        # unhealthy. The audit invariant is enforced on the write path.
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIs(body["ready"], False)
        self.assertIs(body["audit_writable"], False)
        self.assertIsNone(body["unreconciled_outcome_unknown_count"])

    def test_a_missing_session_secret_still_fails_fast(self) -> None:
        environment = self.environment()
        environment.pop("SESSION_SECRET")
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(RuntimeError):
                create_production_app()


class HealthGateTests(unittest.TestCase):
    """The gate is 200 if and only if the audit store proved it can write."""

    def client(self, repository: object) -> TestClient:
        with mock.patch.dict(os.environ, SECRET_ENVIRONMENT, clear=False):
            return TestClient(create_app(audit_repository=repository))

    def test_no_repository_at_all_is_503(self) -> None:
        response = self.client(None).get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.json()["ready"], False)

    def test_an_unreadable_count_is_reported_as_unknown_never_as_zero(
        self,
    ) -> None:
        class Raising:
            async def is_writable(self) -> bool:
                return False

            async def unreconciled_attempt_count(self) -> int:
                raise AuditStorageUnavailable("cannot reach storage")

        response = self.client(Raising()).get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.json()["unreconciled_outcome_unknown_count"])

    def test_a_probe_that_raises_is_never_reported_as_healthy(self) -> None:
        class Raising:
            async def is_writable(self) -> bool:
                raise AuditStorageUnavailable("cannot reach storage")

            async def unreconciled_attempt_count(self) -> int:
                return 0

        response = self.client(Raising()).get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.json()["audit_writable"], False)

    def test_unreconciled_attempts_do_not_by_themselves_fail_the_gate(
        self,
    ) -> None:
        # A recorded outcome_unknown is the invariant working, not a fault:
        # readiness is write capability, and the count is reported for the
        # operator rather than used to hold the service down.
        class Writable:
            async def is_writable(self) -> bool:
                return True

            async def unreconciled_attempt_count(self) -> int:
                return 3

        response = self.client(Writable()).get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unreconciled_outcome_unknown_count"], 3)


if __name__ == "__main__":
    unittest.main()
