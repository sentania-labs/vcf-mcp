import pytest
import os
from unittest import mock
from starlette.testclient import TestClient
from vcf_ops_mcp.app import create_app

class MockAuditRepository:
    def __init__(self, is_writable: bool, unreconciled_count: int):
        self._is_writable = is_writable
        self._unreconciled_count = unreconciled_count

    async def is_writable(self) -> bool:
        return self._is_writable

    async def unreconciled_attempt_count(self) -> int:
        return self._unreconciled_count

@pytest.mark.asyncio
async def test_healthz_healthy():
    with mock.patch.dict(os.environ, {"SESSION_SECRET": "test-secret"}):
        repo = MockAuditRepository(is_writable=True, unreconciled_count=0)
        app = create_app(audit_repository=repo)
    client = TestClient(app)
    
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["audit_writable"] is True
    assert data["unreconciled_outcome_unknown_count"] == 0

@pytest.mark.asyncio
async def test_healthz_unhealthy_audit():
    with mock.patch.dict(os.environ, {"SESSION_SECRET": "test-secret"}):
        repo = MockAuditRepository(is_writable=False, unreconciled_count=2)
        app = create_app(audit_repository=repo)
    client = TestClient(app)
    
    response = client.get("/healthz")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["audit_writable"] is False
    assert data["unreconciled_outcome_unknown_count"] == 2
