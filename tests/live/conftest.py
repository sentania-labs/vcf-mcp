"""Live tier wiring: opt-in, host-allowlisted, and read-set-hooked.

Tier 3 per SPEC section 11. Never runs in CI. Run it by hand at every gate and
after every appliance upgrade:

    VCF_MCP_LIVE=1 \\
    VCF_MCP_LIVE_HOST=vcf-lab-operations-devel.int.sentania.net \\
    VCF_MCP_LIVE_CREDENTIALS_FILE=/path/outside/the/repo/creds.txt \\
    PYTHONPATH=src python3 -m pytest tests/live -m live

Credentials come from the environment or from a file outside the repository
worktree. They are never defaulted to a path inside it, never echoed, and never
placed in an assertion message.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from tests.live.guard import assert_host_is_permitted, refuse_outside_the_read_set
from vcf_mcp.contracts import (
    ConfigurationGeneration,
    TargetId,
    TargetPosture,
    TargetRecord,
)
from vcf_mcp.vcf.adapters import READ_ALLOWLIST
from vcf_mcp.vcf.client import SUITE_API_ROOT, TargetCredentials, VcfTargetClient


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: opt-in read-only test against the DEVEL appliance"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if os.environ.get("VCF_MCP_LIVE") == "1":
        return
    skip = pytest.mark.skip(
        reason="live tier is opt-in: set VCF_MCP_LIVE=1 and VCF_MCP_LIVE_HOST"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def _credentials_from_file(path: str, section: str) -> tuple[str, str]:
    username = password = None
    current = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("["):
                current = line.split("]")[0].strip("[").strip().upper()
                continue
            if current != section or ":" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            if key.strip() == "username":
                username = value.strip()
            elif key.strip() == "password":
                password = value.strip()
    if not username or not password:
        raise AssertionError(
            f"the credentials file has no complete [{section}] section"
        )
    return username, password


@pytest.fixture(scope="session")
def live_host() -> str:
    """The configured host, refused unless it is on the allowlist."""

    configured = os.environ.get("VCF_MCP_LIVE_HOST")
    if not configured:
        pytest.skip("VCF_MCP_LIVE_HOST is not set")
    return assert_host_is_permitted(configured)


@pytest.fixture(scope="session")
def live_credentials() -> TargetCredentials:
    username = os.environ.get("VCF_MCP_LIVE_USERNAME")
    password = os.environ.get("VCF_MCP_LIVE_PASSWORD")
    if not (username and password):
        path = os.environ.get("VCF_MCP_LIVE_CREDENTIALS_FILE")
        if not path:
            pytest.skip(
                "set VCF_MCP_LIVE_USERNAME and VCF_MCP_LIVE_PASSWORD, or "
                "VCF_MCP_LIVE_CREDENTIALS_FILE"
            )
        username, password = _credentials_from_file(
            path, os.environ.get("VCF_MCP_LIVE_SECTION", "DEVEL")
        )
    return TargetCredentials(
        username, password, os.environ.get("VCF_MCP_LIVE_AUTH_SOURCE", "LOCAL")
    )


@pytest.fixture(scope="session")
def live_target(live_host: str) -> TargetRecord:
    return TargetRecord(
        id=TargetId("live-devel"),
        name="devel",
        fqdn=live_host,
        posture=TargetPosture.READ_ONLY,
        is_prod=False,
        # DEVEL presents a self-signed certificate that does not validate
        # against the host trust store. The honest live-tier posture is the
        # same per-target verification-disabled boolean the product ships,
        # which is SPEC section 7's open question for the principal.
        verify_ssl=False,
        auth_source="LOCAL",
        configuration_generation=ConfigurationGeneration(1),
    )


class LiveSession:
    """One client and one event loop for the whole live run.

    Deliberately not built on an async test plugin: the live tier must run from
    a bare checkout with nothing but pytest and the runtime dependencies, and a
    plugin that is absent would look like a skipped gate rather than a failure.
    """

    def __init__(self, client: VcfTargetClient, loop) -> None:
        self.client = client
        self._loop = loop

    def run(self, awaitable):
        return self._loop.run_until_complete(awaitable)


@pytest.fixture(scope="session")
def live(live_target: TargetRecord, live_credentials: TargetCredentials):
    """A real client whose transport refuses anything outside the read set."""

    loop = asyncio.new_event_loop()
    http = httpx.AsyncClient(
        base_url=f"https://{live_target.fqdn}{SUITE_API_ROOT}",
        verify=live_target.verify_ssl,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        event_hooks={"request": [refuse_outside_the_read_set]},
    )
    client = VcfTargetClient(
        target=live_target,
        credentials=live_credentials,
        allowlist=READ_ALLOWLIST,
        http_client=http,
    )
    session = LiveSession(client, loop)
    try:
        yield session
    finally:
        loop.run_until_complete(client.aclose())
        loop.close()
