"""Storage-level tests for the durable SQLite audit repository.

The reconciliation and write-probe behavior here is the part the health gate
depends on, so these tests exercise real files on disk rather than doubles: a
write probe that passes against an in-memory stand-in proves nothing about a
volume the container cannot write to.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vcf_ops_mcp.audit import (
    RECOVERY_ERROR_CODE,
    SCHEMA_VERSION,
    AuditStorageUnavailable,
    SqliteAuditRepository,
    audit_db_path_from_environment,
)
from vcf_ops_mcp.audit.sqlite_repository import DEFAULT_AUDIT_DB_PATH
from vcf_ops_mcp.contracts import (
    AuditRecord,
    AuditStatus,
    CorrelationId,
    KeyId,
    TargetId,
)


# The permission-based probes below prove nothing as root, which ignores the
# mode bits they rely on. The container runs as uid 10001, so the real
# deployment is always the non-root case; a root CI runner skips them rather
# than asserting a false pass.
requires_unprivileged = unittest.skipIf(
    os.geteuid() == 0, "file mode bits do not constrain root"
)

AT = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
RECOVERED_AT = AT + timedelta(minutes=5)


def record(
    correlation_id: str,
    status: AuditStatus,
    *,
    at: datetime = AT,
    error_code: str | None = None,
    latency_ms: int | None = None,
) -> AuditRecord:
    return AuditRecord(
        correlation_id=CorrelationId(correlation_id),
        key_id=KeyId("key-1"),
        target_id=TargetId("target-1"),
        tool_name="list_resources",
        arguments_digest="sha256:" + "0" * 64,
        status=status,
        timestamp=at,
        error_code=error_code,
        latency_ms=latency_ms,
        projection_version="v1",
        skill_content_digest=None,
    )


class SqliteAuditRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "audit" / "audit.sqlite3"
        self.repo = SqliteAuditRepository(self.path)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.repo.close)

    # -- schema and durability --------------------------------------------

    async def test_open_creates_the_parent_directory_and_schema(self) -> None:
        self.repo.open()
        self.assertTrue(self.path.exists())
        with sqlite3.connect(self.path) as connection:
            version = connection.execute(
                "SELECT version FROM schema_version"
            ).fetchone()
            journal = connection.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(version[0], SCHEMA_VERSION)
        self.assertEqual(journal[0].lower(), "wal")

    async def test_open_is_idempotent(self) -> None:
        self.repo.open()
        self.repo.open()
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 0)

    async def test_unsupported_schema_version_refuses_to_open(self) -> None:
        self.repo.open()
        self.repo.close()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE schema_version SET version = 99")
            connection.commit()
        with self.assertRaises(AuditStorageUnavailable):
            SqliteAuditRepository(self.path).open()

    async def test_appended_record_round_trips_through_a_new_process(
        self,
    ) -> None:
        self.repo.open()
        await self.repo.append_committed(record("c1", AuditStatus.ATTEMPT))
        self.repo.close()

        reopened = SqliteAuditRepository(self.path)
        self.addCleanup(reopened.close)
        reopened.open()
        attempts = await reopened.unreconciled_attempts()
        self.assertEqual(len(attempts), 1)
        stored = attempts[0]
        self.assertEqual(stored.correlation_id, "c1")
        self.assertEqual(stored.key_id, "key-1")
        self.assertEqual(stored.target_id, "target-1")
        self.assertEqual(stored.tool_name, "list_resources")
        self.assertEqual(stored.status, AuditStatus.ATTEMPT)
        self.assertEqual(stored.timestamp, AT)
        self.assertEqual(stored.projection_version, "v1")

    async def test_optional_fields_survive_a_round_trip(self) -> None:
        self.repo.open()
        await self.repo.append_committed(record("c1", AuditStatus.ATTEMPT))
        await self.repo.append_committed(
            record(
                "c1", AuditStatus.ERROR, error_code="handler_error", latency_ms=42
            )
        )
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT error_code, latency_ms FROM audit_records"
                " WHERE status = ?",
                (AuditStatus.ERROR.value,),
            ).fetchone()
        self.assertEqual(row, ("handler_error", 42))

    # -- is_writable is a real probe --------------------------------------

    async def test_is_writable_commits_a_real_write(self) -> None:
        self.repo.open()
        self.assertTrue(await self.repo.is_writable())
        with sqlite3.connect(self.path) as connection:
            probes = connection.execute(
                "SELECT COUNT(*) FROM write_probe"
            ).fetchone()
            ledger = connection.execute(
                "SELECT COUNT(*) FROM audit_records"
            ).fetchone()
        self.assertEqual(probes[0], 1)
        # The probe must never pollute the ledger.
        self.assertEqual(ledger[0], 0)

    async def test_is_writable_is_false_when_the_store_cannot_be_opened(
        self,
    ) -> None:
        # A path whose parent is a regular file cannot be created at all, which
        # stands in for a volume the container has no write access to.
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        repo = SqliteAuditRepository(blocker / "audit.sqlite3")
        self.addCleanup(repo.close)
        self.assertFalse(await repo.is_writable())

    @requires_unprivileged
    async def test_is_writable_is_false_against_a_read_only_database(
        self,
    ) -> None:
        self.repo.open()
        self.repo.close()
        self.path.chmod(0o444)
        self.path.parent.chmod(0o555)
        self.addCleanup(self.path.parent.chmod, 0o755)
        repo = SqliteAuditRepository(self.path)
        self.addCleanup(repo.close)
        self.assertFalse(await repo.is_writable())

    async def test_append_raises_rather_than_dropping_a_record(self) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        repo = SqliteAuditRepository(blocker / "audit.sqlite3")
        self.addCleanup(repo.close)
        with self.assertRaises(AuditStorageUnavailable):
            await repo.append_committed(record("c1", AuditStatus.ATTEMPT))

    async def test_counting_an_unreachable_store_raises_and_never_returns_zero(
        self,
    ) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        repo = SqliteAuditRepository(blocker / "audit.sqlite3")
        self.addCleanup(repo.close)
        with self.assertRaises(AuditStorageUnavailable):
            await repo.unreconciled_attempt_count()

    @requires_unprivileged
    async def test_a_repaired_store_recovers_without_a_restart(self) -> None:
        self.repo.open()
        self.repo.close()
        self.path.parent.chmod(0o555)
        self.path.chmod(0o444)
        repo = SqliteAuditRepository(self.path)
        self.addCleanup(repo.close)
        self.assertFalse(await repo.is_writable())
        self.path.parent.chmod(0o755)
        self.path.chmod(0o644)
        self.assertTrue(await repo.is_writable())

    # -- reconciliation ---------------------------------------------------

    async def test_an_attempt_with_a_terminal_record_is_reconciled(
        self,
    ) -> None:
        self.repo.open()
        for terminal in (
            AuditStatus.OK,
            AuditStatus.DENIED,
            AuditStatus.ERROR,
            AuditStatus.TIMEOUT,
            AuditStatus.CANCELLED,
            AuditStatus.OUTCOME_UNKNOWN,
        ):
            correlation_id = f"c-{terminal.value}"
            await self.repo.append_committed(
                record(correlation_id, AuditStatus.ATTEMPT)
            )
            await self.repo.append_committed(record(correlation_id, terminal))
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 0)
        self.assertEqual(
            await self.repo.close_unreconciled_attempts(
                recovered_at=RECOVERED_AT
            ),
            0,
        )

    async def test_an_attempt_without_a_terminal_record_is_unreconciled(
        self,
    ) -> None:
        self.repo.open()
        await self.repo.append_committed(record("open", AuditStatus.ATTEMPT))
        await self.repo.append_committed(record("closed", AuditStatus.ATTEMPT))
        await self.repo.append_committed(record("closed", AuditStatus.OK))

        attempts = await self.repo.unreconciled_attempts()
        self.assertEqual([a.correlation_id for a in attempts], ["open"])
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 1)

    async def test_duplicate_attempts_count_once_per_call(self) -> None:
        self.repo.open()
        await self.repo.append_committed(record("c1", AuditStatus.ATTEMPT))
        await self.repo.append_committed(record("c1", AuditStatus.ATTEMPT))
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 1)
        self.assertEqual(
            await self.repo.close_unreconciled_attempts(
                recovered_at=RECOVERED_AT
            ),
            1,
        )
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 0)

    async def test_recovery_appends_outcome_unknown_and_never_rewrites(
        self,
    ) -> None:
        self.repo.open()
        await self.repo.append_committed(record("open", AuditStatus.ATTEMPT))

        closed = await self.repo.close_unreconciled_attempts(
            recovered_at=RECOVERED_AT
        )
        self.assertEqual(closed, 1)

        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT status, timestamp, error_code, latency_ms, tool_name,"
                " key_id, target_id, arguments_digest"
                " FROM audit_records ORDER BY id"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        # The attempt row is untouched.
        self.assertEqual(rows[0][0], AuditStatus.ATTEMPT.value)
        self.assertEqual(rows[0][1], AT.isoformat())
        # The terminal row is appended, carries the recovery time and reason,
        # and claims no latency it cannot know.
        self.assertEqual(rows[1][0], AuditStatus.OUTCOME_UNKNOWN.value)
        self.assertEqual(rows[1][1], RECOVERED_AT.isoformat())
        self.assertEqual(rows[1][2], RECOVERY_ERROR_CODE)
        self.assertIsNone(rows[1][3])
        # Identity of the original call is carried forward verbatim.
        self.assertEqual(rows[0][4:], rows[1][4:])

    async def test_recovery_never_infers_a_successful_outcome(self) -> None:
        self.repo.open()
        await self.repo.append_committed(record("open", AuditStatus.ATTEMPT))
        await self.repo.close_unreconciled_attempts(recovered_at=RECOVERED_AT)
        with sqlite3.connect(self.path) as connection:
            successes = connection.execute(
                "SELECT COUNT(*) FROM audit_records WHERE status = ?",
                (AuditStatus.OK.value,),
            ).fetchone()
        self.assertEqual(successes[0], 0)

    async def test_recovery_is_idempotent(self) -> None:
        self.repo.open()
        await self.repo.append_committed(record("open", AuditStatus.ATTEMPT))
        self.assertEqual(
            await self.repo.close_unreconciled_attempts(
                recovered_at=RECOVERED_AT
            ),
            1,
        )
        self.assertEqual(
            await self.repo.close_unreconciled_attempts(
                recovered_at=RECOVERED_AT
            ),
            0,
        )
        with sqlite3.connect(self.path) as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM audit_records"
            ).fetchone()
        self.assertEqual(total[0], 2)

    async def test_recovery_closes_every_open_attempt(self) -> None:
        self.repo.open()
        for index in range(5):
            await self.repo.append_committed(
                record(f"open-{index}", AuditStatus.ATTEMPT)
            )
        await self.repo.append_committed(record("done", AuditStatus.ATTEMPT))
        await self.repo.append_committed(record("done", AuditStatus.OK))

        self.assertEqual(
            await self.repo.close_unreconciled_attempts(
                recovered_at=RECOVERED_AT
            ),
            5,
        )
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 0)

    async def test_a_lazily_opened_store_reconciles_before_reporting_ready(
        self,
    ) -> None:
        # The Codex review case: bootstrap never ran (or failed), so nothing
        # reconciled the ledger, and the store opens lazily on first use. It
        # must not be able to report itself writable while a prior process's
        # attempt still has no terminal record.
        crashed = SqliteAuditRepository(self.path)
        crashed.open()
        await crashed.append_committed(record("in-flight", AuditStatus.ATTEMPT))
        crashed.close()

        restarted = SqliteAuditRepository(self.path)
        self.addCleanup(restarted.close)
        self.assertTrue(await restarted.is_writable())
        self.assertEqual(await restarted.unreconciled_attempt_count(), 0)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT error_code FROM audit_records WHERE status = ?",
                (AuditStatus.OUTCOME_UNKNOWN.value,),
            ).fetchone()
        self.assertEqual(row[0], RECOVERY_ERROR_CODE)

    @requires_unprivileged
    async def test_a_store_repaired_without_a_restart_reconciles(self) -> None:
        # Bootstrap fails against a ledger that already holds an open attempt,
        # then the operator repairs the volume and does not restart. The lazy
        # reopen has to reconcile, or the health gate would answer 200 with
        # that attempt permanently unterminated.
        crashed = SqliteAuditRepository(self.path)
        crashed.open()
        await crashed.append_committed(record("in-flight", AuditStatus.ATTEMPT))
        crashed.close()
        self.path.chmod(0o444)
        self.path.parent.chmod(0o555)
        self.addCleanup(self.path.parent.chmod, 0o755)

        repo = SqliteAuditRepository(self.path)
        self.addCleanup(repo.close)
        with self.assertRaises((sqlite3.Error, OSError)):
            repo.bootstrap(recovered_at=RECOVERED_AT)
        self.assertFalse(await repo.is_writable())

        self.path.parent.chmod(0o755)
        self.path.chmod(0o644)

        self.assertTrue(await repo.is_writable())
        self.assertEqual(await repo.unreconciled_attempt_count(), 0)

    async def test_appending_reconciles_a_store_that_never_bootstrapped(
        self,
    ) -> None:
        crashed = SqliteAuditRepository(self.path)
        crashed.open()
        await crashed.append_committed(record("in-flight", AuditStatus.ATTEMPT))
        crashed.close()

        restarted = SqliteAuditRepository(self.path)
        self.addCleanup(restarted.close)
        await restarted.append_committed(record("new", AuditStatus.ATTEMPT))
        attempts = await restarted.unreconciled_attempts()
        self.assertEqual([a.correlation_id for a in attempts], ["new"])

    async def test_reconciliation_runs_once_per_open_not_once_per_call(
        self,
    ) -> None:
        self.repo.bootstrap(recovered_at=RECOVERED_AT)
        await self.repo.append_committed(record("open", AuditStatus.ATTEMPT))
        # Already reconciled for this connection, so the probe must not close
        # an attempt the dispatcher is still working on.
        self.assertTrue(await self.repo.is_writable())
        self.assertEqual(await self.repo.unreconciled_attempt_count(), 1)

    async def test_inserts_do_not_touch_sqlite_sequence(self) -> None:
        # AUTOINCREMENT would dirty an extra sqlite_sequence page per insert,
        # which dispatcher/reservations.py does not reserve. Ids stay monotonic
        # without it because this module never deletes a row.
        self.repo.open()
        await self.repo.append_committed(record("c1", AuditStatus.ATTEMPT))
        await self.repo.append_committed(record("c2", AuditStatus.ATTEMPT))
        with sqlite3.connect(self.path) as connection:
            sequences = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_sequence'"
            ).fetchone()
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM audit_records ORDER BY id"
                )
            ]
        self.assertEqual(sequences[0], 0)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), 2)

    # -- bootstrap, the composition root's entry point --------------------

    async def test_bootstrap_opens_and_reconciles_a_prior_process_crash(
        self,
    ) -> None:
        crashed = SqliteAuditRepository(self.path)
        crashed.open()
        await crashed.append_committed(record("in-flight", AuditStatus.ATTEMPT))
        crashed.close()

        restarted = SqliteAuditRepository(self.path)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.bootstrap(recovered_at=RECOVERED_AT), 1)
        self.assertEqual(await restarted.unreconciled_attempt_count(), 0)
        self.assertTrue(await restarted.is_writable())

    async def test_bootstrap_on_a_clean_store_closes_nothing(self) -> None:
        self.assertEqual(self.repo.bootstrap(recovered_at=RECOVERED_AT), 0)
        self.assertTrue(await self.repo.is_writable())

    async def test_bootstrap_raises_when_storage_is_unavailable(self) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        repo = SqliteAuditRepository(blocker / "audit.sqlite3")
        self.addCleanup(repo.close)
        with self.assertRaises((sqlite3.Error, OSError)):
            repo.bootstrap(recovered_at=RECOVERED_AT)


class AuditPathResolutionTests(unittest.TestCase):
    def test_default_path_is_on_the_audit_volume(self) -> None:
        self.assertEqual(audit_db_path_from_environment({}), DEFAULT_AUDIT_DB_PATH)
        self.assertEqual(DEFAULT_AUDIT_DB_PATH, Path("/audit/audit.sqlite3"))

    def test_environment_overrides_the_default(self) -> None:
        self.assertEqual(
            audit_db_path_from_environment({"AUDIT_DB_PATH": "/tmp/a.sqlite3"}),
            Path("/tmp/a.sqlite3"),
        )

    def test_an_empty_override_falls_back_to_the_default(self) -> None:
        self.assertEqual(
            audit_db_path_from_environment({"AUDIT_DB_PATH": ""}),
            DEFAULT_AUDIT_DB_PATH,
        )


if __name__ == "__main__":
    unittest.main()
