from __future__ import annotations

import asyncio
import re
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from starlette.testclient import TestClient

from vcf_mcp.app import create_app
from vcf_mcp.audit import SqliteAuditRepository
from vcf_mcp.backend_packs import load_backend_packs
from vcf_mcp.contracts import AuditStatus, BackendKind
from vcf_mcp.declared_backend import DeclaredBackendClient
from vcf_mcp.mcp_server import implemented_scopes
from vcf_mcp.runtime_repository import RuntimeRepository
from vcf_mcp.target_verification import TargetVerifier


def _synthetic_ca_pem(common_name: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
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


def _transport_failure(request: httpx.Request, outcome: str) -> None:
    if outcome == "cannot_resolve":
        try:
            raise socket.gaierror(-2, "fixture hostname not found")
        except socket.gaierror as cause:
            raise httpx.ConnectError("fixture resolution failure", request=request) from cause
    if outcome == "cannot_connect":
        raise httpx.ConnectError("fixture connection refused", request=request)
    if outcome == "certificate_not_trusted":
        try:
            raise ssl.SSLCertVerificationError("fixture certificate verify failed")
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED", request=request) from cause


def _verifier(
    audit: SqliteAuditRepository,
    outcome: str,
    *,
    observed_trust: list[str | None] | None = None,
    timeout_seconds: float = 0.2,
) -> TargetVerifier:
    packs = load_backend_packs()

    async def handler(request: httpx.Request) -> httpx.Response:
        _transport_failure(request, outcome)
        if outcome == "timeout":
            await asyncio.sleep(1)
        if request.method == "POST" and request.url.path.endswith("/auth/token/acquire"):
            if outcome == "credential_rejected":
                return httpx.Response(401, json={"message": "fixture refusal"})
            return httpx.Response(200, json={"token": "fixture-token"})
        if outcome == "unexpected_response":
            return httpx.Response(502, json={"message": "fixture upstream error"})
        return httpx.Response(200, json={"items": []})

    def factory(target, credentials, pack, root_ca_pem):
        if observed_trust is not None:
            observed_trust.append(root_ca_pem)
        return DeclaredBackendClient(
            target=target,
            credentials=credentials,
            pack=pack,
            http_client=httpx.AsyncClient(
                base_url=f"https://{target.fqdn}",
                transport=httpx.MockTransport(handler),
            ),
        )

    return TargetVerifier(
        packs=packs,
        audit_repository=audit,
        client_factory=factory,
        timeout_seconds=timeout_seconds,
    )


def _runtime_and_audit(
    tmp_path: Path,
) -> tuple[RuntimeRepository, SqliteAuditRepository]:
    runtime = RuntimeRepository(
        tmp_path / "data" / "config.sqlite3",
        tmp_path / "keys" / "credential_keyring.json",
        grantable_scopes=implemented_scopes(),
    )
    runtime.bootstrap()
    asyncio.run(runtime.set_admin_password_for_test("synthetic-admin-password"))
    audit = SqliteAuditRepository(tmp_path / "audit" / "audit.sqlite3")
    audit.bootstrap(recovered_at=datetime.now(UTC))
    return runtime, audit


def _login_and_csrf(client: TestClient) -> str:
    login = client.post(
        "/admin/login",
        data={"username": "admin", "password": "synthetic-admin-password"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    dashboard = client.get("/admin?tab=targets")
    match = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.text)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        ("credential_rejected", "rejected the credential"),
        ("cannot_resolve", "Cannot resolve the backend hostname"),
        ("cannot_connect", "Cannot connect to the backend"),
        ("certificate_not_trusted", "certificate is not trusted"),
        ("unexpected_response", "reachable but returned an unexpected response"),
    ],
)
def test_registration_failure_reports_cause_and_stores_nothing(
    tmp_path: Path, outcome: str, message: str
) -> None:
    runtime, audit = _runtime_and_audit(tmp_path)
    app = create_app(
        audit_repository=audit,
        target_verifier=_verifier(audit, outcome),
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post(
                "/admin/targets",
                data={
                    "csrf_token": _login_and_csrf(client),
                    "backend": BackendKind.OPS.value,
                    "name": "fixture",
                    "fqdn": "fixture.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-rejected-password",
                    "auth_source": "LOCAL",
                    "verify_ssl": "on",
                },
            )
            assert response.status_code == 400
            assert message in response.text
            assert "Nothing was saved" in response.text
        assert asyncio.run(runtime.list()) == ()
        records = asyncio.run(audit.recent_records(limit=2))
        assert {record.status for record in records} >= {AuditStatus.ATTEMPT}
        assert records[0].error_code == f"target_verification_{outcome}"
        assert b"synthetic-rejected-password" not in (
            tmp_path / "audit" / "audit.sqlite3"
        ).read_bytes()
    finally:
        runtime.close()
        audit.close()


def test_success_uses_additive_trust_stores_timestamp_and_can_recheck(
    tmp_path: Path,
) -> None:
    runtime, audit = _runtime_and_audit(tmp_path)
    global_ca = _synthetic_ca_pem("fixture global CA")
    target_ca = _synthetic_ca_pem("fixture target CA")
    asyncio.run(runtime.set_global_root_ca(global_ca))
    observed_trust: list[str | None] = []
    app = create_app(
        audit_repository=audit,
        target_verifier=_verifier(
            audit, "success", observed_trust=observed_trust
        ),
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login_and_csrf(client)
            registered = client.post(
                "/admin/targets",
                data={
                    "csrf_token": csrf,
                    "backend": BackendKind.OPS.value,
                    "name": "fixture",
                    "fqdn": "fixture.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-password",
                    "auth_source": "LOCAL",
                    "verify_ssl": "on",
                },
                files={"root_ca": ("target.pem", target_ca, "application/x-pem-file")},
                follow_redirects=False,
            )
            assert registered.status_code == 303
            target = asyncio.run(runtime.list())[0]
            assert target.last_verified_at is not None
            page = client.get("/admin?tab=targets")
            assert str(target.last_verified_at) in page.text
            csrf = re.search(
                r'name="csrf_token" value="([^"]+)"', page.text
            ).group(1)
            rechecked = client.post(
                f"/admin/targets/{target.id}/verify",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
            assert rechecked.status_code == 303
        assert observed_trust == [global_ca + target_ca, global_ca + target_ca]
        records = asyncio.run(audit.recent_records(limit=4))
        assert [record.status for record in records].count(AuditStatus.OK) == 2
    finally:
        runtime.close()
        audit.close()


def test_failed_edit_keeps_existing_host_and_credential(
    tmp_path: Path,
) -> None:
    runtime, audit = _runtime_and_audit(tmp_path)
    target = asyncio.run(
        runtime.create_target(
            name="existing",
            fqdn="existing.example.internal",
            username="synthetic-old-user",
            password="synthetic-old-password",
            auth_source="LOCAL",
            verify_ssl=False,
            backend=BackendKind.OPS,
        )
    )
    app = create_app(
        audit_repository=audit,
        target_verifier=_verifier(audit, "credential_rejected"),
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post(
                f"/admin/targets/{target.id}",
                data={
                    "csrf_token": _login_and_csrf(client),
                    "configuration_generation": "1",
                    "name": "changed",
                    "fqdn": "changed.example.internal",
                    "username": "synthetic-new-user",
                    "password": "synthetic-new-password",
                    "auth_source": "LOCAL",
                    "posture": "read_only",
                },
            )
            assert response.status_code == 400
            assert "rejected the credential" in response.text
        unchanged = asyncio.run(runtime.get(target.id))
        credentials = asyncio.run(runtime.get_credentials(target.id))
        assert unchanged is not None
        assert unchanged.name == "existing"
        assert unchanged.fqdn == "existing.example.internal"
        assert unchanged.configuration_generation == 1
        assert unchanged.auth_failure_count == 0
        assert unchanged.auth_locked is False
        assert credentials.acquire_payload()["username"] == "synthetic-old-user"
        assert credentials.acquire_payload()["password"] == "synthetic-old-password"
    finally:
        runtime.close()
        audit.close()


def test_verification_timeout_is_bounded_and_visible(tmp_path: Path) -> None:
    runtime, audit = _runtime_and_audit(tmp_path)
    app = create_app(
        audit_repository=audit,
        target_verifier=_verifier(audit, "timeout", timeout_seconds=1.0),
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post(
                "/admin/targets",
                data={
                    "csrf_token": _login_and_csrf(client),
                    "backend": BackendKind.OPS.value,
                    "name": "fixture",
                    "fqdn": "fixture.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-password",
                    "auth_source": "LOCAL",
                },
            )
        assert response.status_code == 400
        assert "timed out after 1 seconds" in response.text
        assert asyncio.run(runtime.list()) == ()
        terminal = asyncio.run(audit.recent_records(limit=1))[0]
        assert terminal.status is AuditStatus.TIMEOUT
        assert terminal.error_code == "target_verification_timeout"
    finally:
        runtime.close()
        audit.close()


def test_verification_deadline_includes_required_audit_commits(tmp_path: Path) -> None:
    runtime, audit = _runtime_and_audit(tmp_path)

    class DelayedAudit:
        async def append_committed(self, record) -> None:
            await asyncio.sleep(0.12)
            await audit.append_committed(record)

    app = create_app(
        audit_repository=audit,
        target_verifier=_verifier(DelayedAudit(), "success"),
        session_secret="synthetic-session-secret-with-at-least-32-bytes",
        runtime_repository=runtime,
        mcp_ready=True,
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login_and_csrf(client)
            started = time.monotonic()
            response = client.post(
                "/admin/targets",
                data={
                    "csrf_token": csrf,
                    "backend": BackendKind.OPS.value,
                    "name": "fixture",
                    "fqdn": "fixture.example.internal",
                    "username": "synthetic-reader",
                    "password": "synthetic-password",
                    "auth_source": "LOCAL",
                },
            )
            elapsed = time.monotonic() - started
        assert response.status_code == 503
        assert "audit is unavailable" in response.text
        assert elapsed < 0.5
        assert asyncio.run(runtime.list()) == ()
    finally:
        runtime.close()
        audit.close()
