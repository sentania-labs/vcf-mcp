"""Composition-root and health-gate tests.

These are the first-light tests: they assert that the production entry point
builds an application whose /healthz answers 200 against a real audit store,
and that every way of failing to reach that store answers 503 instead.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.parse
import http.cookiejar
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from vcf_mcp.app import create_app
from vcf_mcp.audit import AuditStorageUnavailable, SqliteAuditRepository
from vcf_mcp.contracts import (
    AuditRecord,
    AuditStatus,
    CorrelationId,
    KeyId,
    TargetId,
)
from vcf_mcp.main import create_production_app
from vcf_mcp.runtime_repository import AllTargetsIntegrityFailed, RuntimeRepository

SECRET_ENVIRONMENT = {"SESSION_SECRET": "synthetic-test-secret-with-more-than-32-bytes"}
UVICORN_STARTUP_TIMEOUT_SECONDS = 30


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
            "AUDIT_DB_PATH": str(self.root / "audit" / "audit.sqlite3"),
            "SESSION_SECRET_PATH": str(self.root / "keys" / "session_secret"),
            "AUDIT_DIGEST_KEY_PATH": str(self.root / "keys" / "audit_digest_key"),
            "CONFIG_DB_PATH": str(self.root / "data" / "config.sqlite3"),
            "CREDENTIAL_KEYRING_PATH": str(
                self.root / "keys" / "credential_keyring.json"
            ),
            "ADMIN_BOOTSTRAP_PASSWORD_FILE": str(
                self.root / "keys" / "admin_bootstrap_password"
            ),
            "SKILLS_PATH": str(Path(__file__).resolve().parents[1] / "skills"),
            "PUBLIC_BASE_URL": "http://testserver",
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

    def test_all_target_integrity_failure_refuses_startup(self) -> None:
        environment = self.environment()
        repository = RuntimeRepository(
            Path(environment["CONFIG_DB_PATH"]),
            Path(environment["CREDENTIAL_KEYRING_PATH"]),
            grantable_scopes=frozenset(),
            bootstrap_password_path=Path(environment["ADMIN_BOOTSTRAP_PASSWORD_FILE"]),
        )
        repository.bootstrap()
        target = asyncio.run(
            repository.create_target(
                name="integrity-failed",
                fqdn="integrity-failed.example.internal",
                username="synthetic-reader",
                password="synthetic-password",
                auth_source="LOCAL",
                verify_ssl=False,
            )
        )
        repository.close()
        with sqlite3.connect(environment["CONFIG_DB_PATH"]) as connection:
            connection.execute(
                "UPDATE targets SET password_envelope = '{\"broken\":true}'"
                " WHERE id = ?",
                (str(target.id),),
            )
            connection.commit()

        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(AllTargetsIntegrityFailed):
                create_production_app()

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
        environment = self.environment(AUDIT_DB_PATH=str(blocker / "audit.sqlite3"))
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

    def test_a_missing_session_secret_is_generated_and_persisted(self) -> None:
        environment = self.environment()
        with mock.patch.dict(os.environ, environment, clear=True):
            first = create_production_app()
            path = Path(environment["SESSION_SECRET_PATH"])
            first_value = path.read_text()
            second = create_production_app()
            second_value = path.read_text()
            with TestClient(first) as client:
                first_health = client.get("/healthz")
            with TestClient(second) as client:
                second_health = client.get("/healthz")
        self.assertEqual(first_value, second_value)
        self.assertGreaterEqual(len(first_value.encode()), 32)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(first_health.status_code, 200)
        self.assertEqual(second_health.status_code, 200)

    def test_every_generated_private_file_has_mode_0600(self) -> None:
        environment = self.environment()
        with mock.patch.dict(os.environ, environment, clear=True):
            create_production_app()

        for setting in (
            "SESSION_SECRET_PATH",
            "AUDIT_DIGEST_KEY_PATH",
            "CREDENTIAL_KEYRING_PATH",
        ):
            path = Path(environment[setting])
            self.assertTrue(path.is_file(), setting)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600, setting)

    def test_private_file_refusal_is_logged_and_reported_by_health(self) -> None:
        environment = self.environment()
        path = Path(environment["SESSION_SECRET_PATH"])
        path.parent.mkdir(parents=True)
        path.write_text("synthetic-session-secret-with-more-than-32-bytes")
        path.chmod(0o604)
        real_chmod = os.chmod

        def refuse_session_secret(target, mode, *args, **kwargs):
            if not isinstance(target, int) and Path(target) == path:
                raise PermissionError("read-only mount")
            return real_chmod(target, mode, *args, **kwargs)

        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch(
                "vcf_mcp.security.os.chmod", side_effect=refuse_session_secret
            ),
            self.assertLogs("vcf_mcp.main", level="ERROR") as captured,
        ):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        reason = response.json()["startup_errors"]["session_secret"]
        for expected in (
            str(path),
            "mode 0604",
            "outside the service group",
            "set mode to 0600",
        ):
            self.assertIn(expected, reason)
            self.assertIn(expected, "\n".join(captured.output))

    def test_an_unwritable_session_secret_path_reports_503(self) -> None:
        blocker = self.root / "secret-blocker"
        blocker.write_text("not a directory")
        environment = self.environment(
            SESSION_SECRET_PATH=str(blocker / "session_secret")
        )
        with mock.patch.dict(os.environ, environment, clear=True):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.json()["session_secret_persistent"], False)

    def test_audit_digest_key_survives_session_secret_rotation(self) -> None:
        environment = self.environment()
        key_path = Path(environment["AUDIT_DIGEST_KEY_PATH"])
        with mock.patch.dict(os.environ, environment, clear=True):
            first = create_production_app()
            first_key = key_path.read_bytes()
            with TestClient(first) as client:
                first_health = client.get("/healthz")
        rotated = self.environment(
            SESSION_SECRET="rotated-synthetic-secret-with-more-than-32-bytes"
        )
        with mock.patch.dict(os.environ, rotated, clear=True):
            second = create_production_app()
            second_key = key_path.read_bytes()
            with TestClient(second) as client:
                second_health = client.get("/healthz")
        self.assertEqual(first_key, second_key)
        self.assertEqual(len(first_key), 32)
        self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(first_health.status_code, 200)
        self.assertEqual(second_health.status_code, 200)

    def test_an_unwritable_audit_digest_key_path_reports_503(self) -> None:
        blocker = self.root / "digest-blocker"
        blocker.write_text("not a directory")
        environment = self.environment(
            AUDIT_DIGEST_KEY_PATH=str(blocker / "audit_digest_key")
        )
        with mock.patch.dict(os.environ, environment, clear=True):
            app = create_production_app()
            with TestClient(app) as client:
                response = client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIs(body["ready"], False)
        self.assertIs(body["mcp_ready"], False)

    def test_real_uvicorn_factory_path_starts_without_session_secret(
        self,
    ) -> None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment = {
            **os.environ,
            **self.environment(),
        }
        environment.pop("SESSION_SECRET", None)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "vcf_mcp.main:create_production_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        response_status = None
        exited_early = False
        output = ""
        try:
            deadline = time.monotonic() + UVICORN_STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    exited_early = True
                    break
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/healthz", timeout=0.5
                    ) as response:
                        response_status = response.status
                    break
                except OSError:
                    time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=5)

        if exited_early:
            self.fail(f"uvicorn exited before health was ready:\n{output}")
        if response_status is None:
            self.fail(
                "uvicorn stayed alive but health was not ready within "
                f"{UVICORN_STARTUP_TIMEOUT_SECONDS} seconds:\n{output}"
            )
        self.assertEqual(response_status, 200)

    def test_operator_restart_is_audited_before_clean_uvicorn_exit(self) -> None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment_values = self.environment(
            PUBLIC_BASE_URL=f"http://127.0.0.1:{port}"
        )
        bootstrap = Path(environment_values["ADMIN_BOOTSTRAP_PASSWORD_FILE"])
        bootstrap.parent.mkdir(parents=True)
        bootstrap.write_text("synthetic-bootstrap-password")
        bootstrap.chmod(0o600)
        environment = {**os.environ, **environment_values}
        environment.pop("SESSION_SECRET", None)
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "from vcf_mcp.runner import run; "
                    f"run(host='127.0.0.1', port={port}, "
                    "graceful_shutdown_seconds=2)"
                ),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = ""
        try:
            deadline = time.monotonic() + UVICORN_STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/healthz", timeout=0.5
                    ).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                self.fail("uvicorn did not become ready for the restart test")

            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
            )
            opener.open(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/admin/login",
                    data=urllib.parse.urlencode(
                        {
                            "username": "admin",
                            "password": "synthetic-bootstrap-password",
                        }
                    ).encode(),
                    method="POST",
                ),
                timeout=5,
            ).close()
            with opener.open(
                f"http://127.0.0.1:{port}/admin", timeout=5
            ) as dashboard:
                dashboard_text = dashboard.read().decode()
            csrf = re.search(
                r'name="csrf_token" value="([^"]+)"', dashboard_text
            )
            self.assertIsNotNone(csrf)
            restart_response = opener.open(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/admin/restart",
                    data=urllib.parse.urlencode(
                        {"csrf_token": csrf.group(1)}
                    ).encode(),
                    method="POST",
                ),
                timeout=5,
            )
            self.assertEqual(restart_response.status, 202)
            self.assertIn(
                "will start the appliance again automatically",
                restart_response.read().decode(),
            )
            output, _ = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                output, _ = process.communicate(timeout=5)

        self.assertEqual(process.returncode, 0, output)
        with sqlite3.connect(environment_values["CONFIG_DB_PATH"]) as connection:
            event = connection.execute(
                "SELECT event_type FROM configuration_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(event, ("operator_restart_requested",))


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
