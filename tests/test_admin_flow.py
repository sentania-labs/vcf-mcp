from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from vcf_ops_mcp.app import create_app
from vcf_ops_mcp.audit import SqliteAuditRepository
from vcf_ops_mcp.mcp_server import implemented_scopes
from vcf_ops_mcp.runtime_repository import RuntimeRepository


def test_bootstrap_login_target_registration_and_key_mint(
    tmp_path: Path,
) -> None:
    bootstrap = tmp_path / "keys" / "admin_bootstrap_password"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("synthetic-bootstrap-password")
    bootstrap.chmod(0o600)
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
        bootstrap_password_path=bootstrap,
    )
    runtime.bootstrap()
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )

    try:
        with TestClient(app, base_url="https://testserver") as client:
            login_page = client.get("/admin/login")
            assert login_page.status_code == 200
            assert "First-run bootstrap" in login_page.text

            login = client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-bootstrap-password",
                },
                follow_redirects=False,
            )
            assert login.status_code == 303
            assert not bootstrap.exists()

            dashboard = client.get("/admin")
            assert dashboard.status_code == 200
            csrf = re.search(
                r'name="csrf_token" value="([^"]+)"', dashboard.text
            )
            assert csrf is not None

            refused = client.post(
                "/admin/targets",
                data={"csrf_token": "wrong"},
            )
            assert refused.status_code == 403

            registered = client.post(
                "/admin/targets",
                data={
                    "csrf_token": csrf.group(1),
                    "name": "devel",
                    "fqdn": "devel.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-target-password",
                    "auth_source": "LOCAL",
                    "verify_ssl": "on",
                },
                follow_redirects=False,
            )
            assert registered.status_code == 303

            dashboard = client.get("/admin")
            csrf = re.search(
                r'name="csrf_token" value="([^"]+)"', dashboard.text
            )
            target_id = re.search(
                r'name="target_id" value="([^"]+)"', dashboard.text
            )
            assert csrf is not None and target_id is not None
            created = client.post(
                "/admin/keys",
                data={
                    "csrf_token": csrf.group(1),
                    "label": "mcp-client",
                    "scope": "read:targets",
                    "target_id": target_id.group(1),
                },
            )
            assert created.status_code == 200
            assert created.headers["cache-control"] == "no-store"
            key = re.search(r"(vok_[a-z0-9]+_[A-Za-z0-9_-]+)", created.text)
            assert key is not None
    finally:
        runtime.close()
        audit.close()


def test_stale_reauth_from_a_post_round_trips_back_to_work(
    tmp_path: Path,
) -> None:
    bootstrap = tmp_path / "keys" / "admin_bootstrap_password"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("synthetic-bootstrap-password")
    bootstrap.chmod(0o600)
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
        bootstrap_password_path=bootstrap,
    )
    runtime.bootstrap()
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )

    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-bootstrap-password",
                },
                follow_redirects=False,
            )
            dashboard = client.get("/admin")
            csrf = re.search(
                r'name="csrf_token" value="([^"]+)"', dashboard.text
            )
            assert csrf is not None

            with mock.patch(
                "vcf_ops_mcp.admin.auth.is_recent_reauth",
                return_value=False,
            ):
                bounced = client.post(
                    "/admin/targets",
                    data={
                        "csrf_token": csrf.group(1),
                        "name": "devel",
                        "fqdn": "devel.example.internal",
                        "username": "synthetic-reader",
                        "password": "synthetic-target-password",
                        "auth_source": "LOCAL",
                        "verify_ssl": "on",
                    },
                    follow_redirects=False,
                )
                assert bounced.status_code == 303
                assert bounced.headers["location"] == "/admin/reauth"

                confirmed = client.post(
                    "/admin/reauth",
                    data={
                        "csrf_token": csrf.group(1),
                        "password": "synthetic-bootstrap-password",
                    },
                    follow_redirects=False,
                )
                assert confirmed.status_code == 303
                assert confirmed.headers["location"] == "/admin"

            registered = client.post(
                "/admin/targets",
                data={
                    "csrf_token": csrf.group(1),
                    "name": "devel",
                    "fqdn": "devel.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-target-password",
                    "auth_source": "LOCAL",
                    "verify_ssl": "on",
                },
                follow_redirects=False,
            )
            assert registered.status_code == 303
            assert registered.headers["location"] == "/admin"
    finally:
        runtime.close()
        audit.close()


def test_login_with_non_ascii_username_is_denied(tmp_path: Path) -> None:
    bootstrap = tmp_path / "keys" / "admin_bootstrap_password"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("synthetic-bootstrap-password")
    bootstrap.chmod(0o600)
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
        bootstrap_password_path=bootstrap,
    )
    runtime.bootstrap()
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )

    try:
        with TestClient(app, base_url="https://testserver") as client:
            denied = client.post(
                "/admin/login",
                data={
                    "username": "ädmin",
                    "password": "synthetic-bootstrap-password",
                },
                follow_redirects=False,
            )
            assert denied.status_code == 401
    finally:
        runtime.close()
        audit.close()


def test_login_retries_leftover_bootstrap_cleanup(tmp_path: Path) -> None:
    bootstrap = tmp_path / "keys" / "admin_bootstrap_password"
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
        bootstrap_password_path=bootstrap,
    )
    runtime.bootstrap()
    asyncio.run(
        runtime.set_admin_password_for_test(
            "synthetic-bootstrap-password"
        )
    )
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text("synthetic-bootstrap-password")
    bootstrap.chmod(0o600)
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )

    try:
        with TestClient(app, base_url="https://testserver") as client:
            login = client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-bootstrap-password",
                },
                follow_redirects=False,
            )
        assert login.status_code == 303
        assert not bootstrap.exists()
    finally:
        runtime.close()
        audit.close()
