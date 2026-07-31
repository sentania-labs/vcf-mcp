"""Durable SQLite-backed implementation of the AuditRepository protocol.

The audit log is a constitutional invariant, not an implementation detail: no
tool path ships without its audit write, and a server that cannot durably
commit an audit record must report itself unhealthy rather than serve calls it
cannot account for. This module is the storage half of that promise.

Three properties are load-bearing and are the reason this is SQLite rather
than an append-only text file:

1. The ledger is append-only. No statement in this module updates or deletes
   a row of ``audit_records``. Closing an unreconciled attempt appends a new
   terminal record rather than rewriting the attempt row, because an audit
   trail a later process can silently overwrite is not an audit trail. The
   only mutable row in the database is the single write-probe row, which
   carries no audit content.
2. Reconciliation is a query against committed storage, not a cached counter.
   An attempt is unreconciled if and only if its correlation id has an
   ``attempt`` row and no row with any other status. That is derived fresh on
   every call.
3. ``is_writable`` performs a real committed write. It probes a dedicated
   single-row table so the probe never pollutes the ledger, and it commits
   with ``synchronous=FULL`` so a True answer means the storage layer actually
   accepted a durable write, not that this object exists. It also reconciles
   first if the connection was opened without reconciling, so a store that
   recovers lazily cannot report ready while old attempts sit open.

The free-space accounting in ``dispatcher/reservations.py`` is derived from
this schema: one table plus three indexes is the four dirty pages per record
that ``DIRTY_PAGES_PER_AUDIT_RECORD`` assumes. Adding an index here means
revisiting that constant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vcf_ops_mcp.contracts import (
    AuditRecord,
    AuditStatus,
    CorrelationId,
    KeyId,
    TargetId,
)


LOGGER = logging.getLogger(__name__)

AUDIT_DB_PATH_ENV = "AUDIT_DB_PATH"
DEFAULT_AUDIT_DB_PATH = Path("/audit/audit.sqlite3")
SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5_000

RECOVERY_ERROR_CODE = "attempt_unreconciled_at_recovery"
"""Error code stamped on every attempt closed by startup reconciliation."""

_RECORD_COLUMNS = (
    "correlation_id",
    "key_id",
    "target_id",
    "tool_name",
    "arguments_digest",
    "status",
    "timestamp",
    "error_code",
    "latency_ms",
    "projection_version",
    "skill_content_digest",
)

_INSERT_SQL = (
    "INSERT INTO audit_records ("
    + ", ".join(_RECORD_COLUMNS)
    + ") VALUES ("
    + ", ".join("?" for _ in _RECORD_COLUMNS)
    + ")"
)

_SELECT_UNRECONCILED_SQL = f"""
SELECT id, {", ".join(_RECORD_COLUMNS)}
FROM audit_records
WHERE status = ?
  AND correlation_id NOT IN (
    SELECT correlation_id FROM audit_records WHERE status <> ?
  )
ORDER BY id
"""

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS audit_records (
        -- A plain INTEGER PRIMARY KEY, deliberately not AUTOINCREMENT.
        -- AUTOINCREMENT would dirty an extra sqlite_sequence page on every
        -- insert, which is a page dispatcher/reservations.py does not reserve
        -- (DIRTY_PAGES_PER_AUDIT_RECORD covers this table plus three
        -- indexes). Near the admission threshold that mismatch could admit a
        -- call and then leave it without room for its terminal commit. The
        -- rowid alias is monotonic anyway here, because this module never
        -- deletes a row, so nothing reuses an id.
        id INTEGER PRIMARY KEY,
        correlation_id TEXT NOT NULL,
        key_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        arguments_digest TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        error_code TEXT,
        latency_ms INTEGER,
        projection_version TEXT,
        skill_content_digest TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS audit_records_correlation_id"
    " ON audit_records (correlation_id)",
    "CREATE INDEX IF NOT EXISTS audit_records_status"
    " ON audit_records (status)",
    "CREATE INDEX IF NOT EXISTS audit_records_timestamp"
    " ON audit_records (timestamp)",
    """
    CREATE TABLE IF NOT EXISTS write_probe (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        probed_at TEXT NOT NULL
    )
    """,
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)",
)


class AuditStorageUnavailable(Exception):
    """Raised when committed audit storage cannot be reached at all.

    Callers must never translate this into a zero count or an empty result
    set. "I cannot tell" and "there is nothing there" are different answers,
    and only one of them is safe to report as healthy.
    """


def audit_db_path_from_environment(
    environment: dict[str, str] | None = None,
) -> Path:
    """Resolve the audit database path, defaulting to the /audit volume."""

    source = os.environ if environment is None else environment
    configured = source.get(AUDIT_DB_PATH_ENV)
    if configured:
        return Path(configured)
    return DEFAULT_AUDIT_DB_PATH


class SqliteAuditRepository:
    """Append-only audit ledger on a single SQLite database file.

    Every public coroutine runs its SQLite work in a worker thread under one
    lock. SQLite admits a single writer at a time anyway, so serializing here
    trades no throughput for a much simpler durability story.

    The synchronous methods (``open``, ``bootstrap``, ``close``) exist for the
    composition root, which runs before the server accepts traffic and has no
    reason to be asynchronous.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._reconciled = False
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    # -- synchronous lifecycle, used by the composition root ---------------

    def open(self) -> None:
        """Connect and ensure the schema exists. Raises on failure."""

        if self._connection is not None:
            return
        parent = self._path.parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self._path,
            timeout=BUSY_TIMEOUT_MS / 1000,
            check_same_thread=False,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            # The production root filesystem is read-only, so SQLite must not
            # look for a temporary file directory it cannot write to.
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            connection.execute("BEGIN IMMEDIATE")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            existing = connection.execute(
                "SELECT version FROM schema_version"
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif existing[0] != SCHEMA_VERSION:
                connection.execute("ROLLBACK")
                connection.close()
                raise AuditStorageUnavailable(
                    "audit schema version "
                    f"{existing[0]} is not supported by this build"
                )
            connection.execute("COMMIT")
        except AuditStorageUnavailable:
            raise
        except BaseException:
            connection.close()
            raise
        self._connection = connection

    def bootstrap(self, *, recovered_at: datetime) -> int:
        """Open storage and reconcile attempts left open by a prior process.

        Returns the number of attempts closed as ``outcome_unknown``. Raises
        if storage cannot be opened or reconciliation cannot be committed;
        the caller decides whether that is fatal.
        """

        self.open()
        return self._reconcile(self._require_connection(), recovered_at)

    def close(self) -> None:
        connection, self._connection = self._connection, None
        self._reconciled = False
        if connection is not None:
            connection.close()

    # -- AuditRepository protocol -----------------------------------------

    async def append_committed(self, record: AuditRecord) -> None:
        """Commit one audit record durably, or raise.

        A record that cannot be committed is never dropped silently: the
        exception propagates to the dispatcher, which refuses the call or
        reports ``outcome_unknown`` rather than proceeding unaudited.
        """

        await self._run(self._append, record)

    async def is_writable(self) -> bool:
        """Probe real durable write capability, never merely liveness."""

        try:
            return await self._run(self._probe_writable)
        except (AuditStorageUnavailable, sqlite3.Error, OSError):
            LOGGER.warning(
                "audit store at %s is not writable", self._path, exc_info=True
            )
            return False

    async def unreconciled_attempt_count(self) -> int:
        return len(await self.unreconciled_attempts())

    async def unreconciled_attempts(self) -> tuple[AuditRecord, ...]:
        return await self._run(self._select_unreconciled)

    async def close_unreconciled_attempts(
        self, *, recovered_at: datetime
    ) -> int:
        return await self._run(self._close_unreconciled, recovered_at)

    async def recent_records(
        self, *, limit: int = 100
    ) -> tuple[AuditRecord, ...]:
        """Return the newest committed ledger rows for the admin UI."""

        bounded = max(1, min(limit, 500))
        return await self._run(self._recent_records, bounded)

    # -- readiness ---------------------------------------------------------

    def _ensure_ready(self) -> sqlite3.Connection:
        """Return a connection that has reconciled since it was opened.

        Reconciliation is not a boot-time-only concern. A process that failed
        to open the store at boot reopens it lazily the moment the volume is
        repaired, and that store can hold attempts an earlier process left
        open. Without this, the reopened repository would report itself
        writable, the health gate would answer 200, and those attempts would
        sit without terminal records forever. So the first use after any open
        reconciles before the store is allowed to call itself ready.
        """

        connection = self._require_connection()
        if not self._reconciled:
            closed = self._reconcile(connection, _utc_now())
            if closed:
                LOGGER.warning(
                    "closed %d audit attempt(s) left open by a prior process"
                    " as outcome_unknown on reopening %s",
                    closed,
                    self._path,
                )
        return connection

    # -- internals ---------------------------------------------------------

    async def _run(self, work: Callable[..., Any], *arguments: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(work, *arguments)

    def _require_connection(self) -> sqlite3.Connection:
        """Return an open connection, retrying the open once if needed.

        Reopening lazily means an operator who repairs the volume gets a
        recovered server without a restart, and a server that never managed
        to open its store keeps reporting itself unhealthy until they do.
        """

        if self._connection is None:
            try:
                self.open()
            except AuditStorageUnavailable:
                raise
            except (sqlite3.Error, OSError) as error:
                raise AuditStorageUnavailable(
                    f"audit store at {self._path} could not be opened"
                ) from error
        connection = self._connection
        if connection is None:
            raise AuditStorageUnavailable(
                f"audit store at {self._path} is unavailable"
            )
        return connection

    def _discard_connection(self) -> None:
        connection, self._connection = self._connection, None
        self._reconciled = False
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def _append(self, record: AuditRecord) -> None:
        connection = self._ensure_ready()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_INSERT_SQL, _row_from_record(record))
            connection.execute("COMMIT")
        except BaseException:
            _rollback_quietly(connection)
            self._discard_connection()
            raise

    def _probe_writable(self, now: datetime | None = None) -> bool:
        connection = self._ensure_ready()
        stamp = (now or _utc_now()).isoformat()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO write_probe (id, probed_at) VALUES (1, ?)"
                " ON CONFLICT (id) DO UPDATE SET probed_at = excluded.probed_at",
                (stamp,),
            )
            connection.execute("COMMIT")
        except BaseException:
            _rollback_quietly(connection)
            self._discard_connection()
            raise
        return True

    def _select_unreconciled(
        self, connection: sqlite3.Connection | None = None
    ) -> tuple[AuditRecord, ...]:
        connection = connection or self._require_connection()
        rows = connection.execute(
            _SELECT_UNRECONCILED_SQL,
            (AuditStatus.ATTEMPT.value, AuditStatus.ATTEMPT.value),
        ).fetchall()
        # A correlation id can carry more than one attempt row if a prior
        # process retried its attempt write. One call owes one terminal
        # record, so the earliest attempt per correlation id is the unit.
        seen: set[str] = set()
        attempts: list[AuditRecord] = []
        for row in rows:
            correlation_id = row[1]
            if correlation_id in seen:
                continue
            seen.add(correlation_id)
            attempts.append(_record_from_row(row[1:]))
        return tuple(attempts)

    def _close_unreconciled(self, recovered_at: datetime) -> int:
        return self._reconcile(self._require_connection(), recovered_at)

    def _recent_records(self, limit: int) -> tuple[AuditRecord, ...]:
        rows = self._require_connection().execute(
            f"SELECT {', '.join(_RECORD_COLUMNS)}"
            " FROM audit_records ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def _reconcile(
        self, connection: sqlite3.Connection, recovered_at: datetime
    ) -> int:
        """Close every open attempt as outcome_unknown, in one transaction.

        Never infers a successful outcome, and never rewrites the attempt: it
        appends one ``outcome_unknown`` terminal record per open attempt. A
        second call finds nothing left to close, so recovery is idempotent.

        Takes its connection as an argument so ``_ensure_ready`` can call it
        without re-entering readiness and recursing.
        """

        try:
            connection.execute("BEGIN IMMEDIATE")
            attempts = self._select_unreconciled(connection)
            for attempt in attempts:
                connection.execute(
                    _INSERT_SQL,
                    _row_from_record(
                        AuditRecord(
                            correlation_id=attempt.correlation_id,
                            key_id=attempt.key_id,
                            target_id=attempt.target_id,
                            tool_name=attempt.tool_name,
                            arguments_digest=attempt.arguments_digest,
                            status=AuditStatus.OUTCOME_UNKNOWN,
                            timestamp=recovered_at,
                            error_code=RECOVERY_ERROR_CODE,
                            projection_version=attempt.projection_version,
                            skill_content_digest=attempt.skill_content_digest,
                        )
                    ),
                )
            connection.execute("COMMIT")
        except BaseException:
            _rollback_quietly(connection)
            self._discard_connection()
            raise
        self._reconciled = True
        return len(attempts)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _rollback_quietly(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _row_from_record(record: AuditRecord) -> tuple[Any, ...]:
    return (
        str(record.correlation_id),
        str(record.key_id),
        str(record.target_id),
        record.tool_name,
        record.arguments_digest,
        record.status.value,
        record.timestamp.isoformat(),
        record.error_code,
        record.latency_ms,
        record.projection_version,
        record.skill_content_digest,
    )


def _record_from_row(row: tuple[Any, ...]) -> AuditRecord:
    return AuditRecord(
        correlation_id=CorrelationId(row[0]),
        key_id=KeyId(row[1]),
        target_id=TargetId(row[2]),
        tool_name=row[3],
        arguments_digest=row[4],
        status=AuditStatus(row[5]),
        timestamp=datetime.fromisoformat(row[6]),
        error_code=row[7],
        latency_ms=row[8],
        projection_version=row[9],
        skill_content_digest=row[10],
    )
