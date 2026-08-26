from __future__ import annotations

import asyncio
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from starlette.testclient import TestClient

from vcf_mcp.admin import auth
from vcf_mcp.app import create_app
from vcf_mcp.audit import SqliteAuditRepository
from vcf_mcp.contracts import AuthorizationMode, BackendKind, InvalidationMode
from vcf_mcp.mcp_server import implemented_scopes
from vcf_mcp.runtime_repository import RuntimeRepository


def synthetic_ca_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture root")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


class RecordingInvalidator:
    def __init__(self) -> None:
        self.calls = []

    async def invalidate(self, change, *, mode):
        self.calls.append((change, mode))


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
            assert "/nsx/mcp" in dashboard.text
            assert "/vsan-dp/mcp" in dashboard.text
            targets_tab = client.get("/admin?tab=targets")
            assert targets_tab.status_code == 200
            assert ">NSX<" in targets_tab.text
            assert "VCF Log Management" in targets_tab.text
            assert "vSAN Data Protection" in targets_tab.text
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', targets_tab.text)
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
            assert registered.headers["location"] == "/admin?tab=targets"
            returned_to_targets = client.get(registered.headers["location"])
            assert "Register backend target" in returned_to_targets.text
            assert (
                'href="/admin?tab=targets" aria-current="page"'
                in returned_to_targets.text
            )

            maintenance_tab = client.get("/admin?tab=maintenance")
            assert "Restart appliance now" in maintenance_tab.text
            assert "Without one, it stays stopped" in maintenance_tab.text
            api_keys_tab = client.get("/admin?tab=api-keys")
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', api_keys_tab.text)
            target_id = re.search(
                r'name="target_id" value="([^"]+)"', api_keys_tab.text
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


def test_tab_urls_reload_and_remain_available_during_degraded_start(
    tmp_path: Path,
) -> None:
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
    )
    runtime.bootstrap()
    asyncio.run(runtime.set_admin_password_for_test("synthetic-admin-password"))
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=False,
        startup_errors={"mcp": "synthetic degraded start"},
    )

    tabs = {
        "overview": "Startup-frozen endpoints",
        "targets": "Register backend target",
        "api-keys": "Mint MCP API key",
        "packs": "Backend pack trust",
        "maintenance": "Credential key rotation",
        "audit": "Recent configuration audit",
    }
    try:
        with TestClient(app, base_url="https://testserver") as client:
            login = client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-admin-password",
                },
                follow_redirects=False,
            )
            assert login.status_code == 303
            assert client.get("/healthz").status_code == 503

            for tab, heading in tabs.items():
                url = f"/admin?tab={tab}"
                first = client.get(url)
                reloaded = client.get(url)
                assert first.status_code == 200
                assert reloaded.status_code == 200
                assert heading in first.text
                assert f'href="{url}" aria-current="page"' in reloaded.text
                for other_heading in tabs.values():
                    assert (other_heading in first.text) is (other_heading == heading)

            invalid = client.get("/admin?tab=not-a-console-area")
            assert invalid.status_code == 200
            assert 'href="/admin?tab=overview" aria-current="page"' in invalid.text
            full_audit = client.get("/admin/audit")
            assert full_audit.status_code == 200
            assert "Recent audit records" in full_audit.text
    finally:
        runtime.close()
        audit.close()


def test_quarantined_target_dashboard_requires_root_ca_recovery(
    tmp_path: Path,
) -> None:
    bootstrap = tmp_path / "keys" / "admin_bootstrap_password"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("synthetic-bootstrap-password")
    bootstrap.chmod(0o600)
    database_path = tmp_path / "data" / "config.sqlite3"
    keyring_path = tmp_path / "keys" / "credential_keyring.json"
    runtime = RuntimeRepository(
        database_path,
        keyring_path,
        grantable_scopes=implemented_scopes(),
        bootstrap_password_path=bootstrap,
    )
    runtime.bootstrap()
    damaged = asyncio.run(
        runtime.create_target(
            name="damaged-ca",
            fqdn="damaged-ca.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=True,
            root_ca_pem=synthetic_ca_pem(),
        )
    )
    asyncio.run(
        runtime.create_target(
            name="healthy",
            fqdn="healthy.example.internal",
            username="synthetic-reader",
            password="synthetic-password",
            auth_source="LOCAL",
            verify_ssl=False,
        )
    )
    runtime.close()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE targets SET root_ca_envelope = '{\"broken\":true}' WHERE id = ?",
            (str(damaged.id),),
        )
        connection.commit()

    runtime = RuntimeRepository(
        database_path,
        keyring_path,
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
            login = client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-bootstrap-password",
                },
                follow_redirects=False,
            )
            assert login.status_code == 303
            dashboard = client.get("/admin?tab=targets")
            assert dashboard.status_code == 200
            assert "replace or remove the stored root CA" in dashboard.text
    finally:
        runtime.close()
        audit.close()


def test_stale_reauth_reports_unsaved_target_and_protects_other_posts(
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
        with mock.patch("time.time") as mock_time:
            mock_time.return_value = 10000.0
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
                csrf = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.text)
                assert csrf is not None

                mock_time.return_value += auth.RECENT_REAUTH_WINDOW_SECONDS + 10
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
                assert asyncio.run(runtime.list()) == ()

                reauth_page = client.get("/admin/reauth")
                assert reauth_page.status_code == 200
                assert auth.DISCARDED_POST_NOTICE in reauth_page.text

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

                returned = client.get(confirmed.headers["location"])
                assert returned.status_code == 200
                assert auth.DISCARDED_POST_NOTICE in returned.text

                stored_bytes = b"".join(
                    path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
                )
                assert b"synthetic-target-password" not in stored_bytes

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
                targets = asyncio.run(runtime.list())
                assert len(targets) == 1
                assert targets[0].fqdn == "devel.example.internal"

                refreshed_dashboard = client.get(registered.headers["location"])
                refreshed_csrf = re.search(
                    r'name="csrf_token" value="([^"]+)"', refreshed_dashboard.text
                )
                assert refreshed_csrf is not None

                mock_time.return_value += auth.RECENT_REAUTH_WINDOW_SECONDS + 10
                other_bounced = client.post(
                    "/admin/authorization-mode",
                    data={
                        "csrf_token": refreshed_csrf.group(1),
                        "authorization_mode": AuthorizationMode.GATEWAY.value,
                    },
                    follow_redirects=False,
                )
                assert other_bounced.status_code == 303
                assert other_bounced.headers["location"] == "/admin/reauth"
                assert (
                    asyncio.run(runtime.authorization_mode()) is AuthorizationMode.LOCAL
                )

                other_reauth_page = client.get("/admin/reauth")
                assert auth.DISCARDED_POST_NOTICE in other_reauth_page.text
    finally:
        runtime.close()
        audit.close()


def test_target_edit_rotates_credentials_uploads_ca_and_cancels_tls_work(
    tmp_path: Path,
) -> None:
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
    )
    runtime.bootstrap()
    asyncio.run(runtime.set_admin_password_for_test("synthetic-admin-password"))
    target = asyncio.run(
        runtime.create_target(
            name="old-vcenter",
            fqdn="old-vcenter.example.internal",
            username="synthetic-old-user",
            password="synthetic-old-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.VCENTER,
        )
    )
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    app = create_app(
        audit_repository=audit,
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    invalidator = RecordingInvalidator()
    app.state.target_invalidator = invalidator
    ca_pem = synthetic_ca_pem()

    try:
        with TestClient(app, base_url="https://testserver") as client:
            login = client.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "synthetic-admin-password",
                },
                follow_redirects=False,
            )
            assert login.status_code == 303
            dashboard = client.get("/admin")
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.text)
            assert csrf is not None
            edited = client.post(
                f"/admin/targets/{target.id}",
                data={
                    "csrf_token": csrf.group(1),
                    "configuration_generation": "1",
                    "name": "new-vcenter",
                    "fqdn": "new-vcenter.example.internal",
                    "username": "synthetic-new-user",
                    "password": "synthetic-new-password",
                    "auth_source": "LOCAL",
                    "posture": "read_only",
                    "verify_ssl": "on",
                },
                files={"root_ca": ("fixture-ca.pem", ca_pem, "application/x-pem-file")},
                follow_redirects=False,
            )
            assert edited.status_code == 303

        updated = asyncio.run(runtime.get(target.id))
        credentials = asyncio.run(runtime.get_credentials(target.id))
        assert updated is not None
        assert updated.name == "new-vcenter"
        assert updated.fqdn == "new-vcenter.example.internal"
        assert updated.verify_ssl is True
        assert updated.has_custom_ca is True
        assert credentials.acquire_payload()["username"] == "synthetic-new-user"
        assert credentials.acquire_payload()["password"] == "synthetic-new-password"
        assert asyncio.run(runtime.get_root_ca(target.id)) == ca_pem
        assert len(invalidator.calls) == 1
        assert invalidator.calls[0][1] is InvalidationMode.CANCEL
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
    asyncio.run(runtime.set_admin_password_for_test("synthetic-bootstrap-password"))
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
