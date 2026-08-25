"""Production composition root.

``create_app`` takes its audit repository as an argument on purpose: that
argument is the seam every test uses to substitute a double. uvicorn's
``--factory`` mode calls its factory with no arguments, so pointing uvicorn at
``create_app`` directly would silently take the default of ``None`` and leave
the server with no audit store at all, which is exactly the 503 this module
exists to fix. Building the store inside ``create_app`` would close the seam
instead. So the wiring lives here, one level above, and the container entry
point names this module.

Boot posture: a server that cannot open its audit store starts anyway, in a
degraded state whose ``/healthz`` answers 503 and says why. It does not
crash-loop. That is not a weakening of the audit invariant, because the
invariant is enforced on the write path rather than at boot: with an
unwritable store the dispatcher's attempt write fails and refuses the call,
and ``StructuralAuditMiddleware`` refuses security-relevant admin writes. A
running container that reports itself unhealthy and logs the reason is
diagnosable; a crash loop answers the edge proxy with an empty 503 and takes
its own logs down with it.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from starlette.applications import Starlette

from vcf_ops_mcp.app import create_app
from vcf_ops_mcp.audit import (
    SqliteAuditRepository,
    audit_db_path_from_environment,
)
from vcf_ops_mcp.mcp_server import build_mcp_surfaces, implemented_scopes
from vcf_ops_mcp.backend_packs import (
    DEFAULT_OPERATOR_PACKS_PATH,
    load_backend_packs,
)
from vcf_ops_mcp.runtime_repository import (
    RuntimeRepository,
    admin_bootstrap_path_from_environment,
    config_db_path_from_environment,
    credential_keyring_path_from_environment,
)
from vcf_ops_mcp.security import (
    load_or_create_audit_digest_key,
    load_or_create_session_secret,
)
from vcf_ops_mcp.skills import load_catalog

LOGGER = logging.getLogger(__name__)

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_PUBLIC_BASE_URL = "http://localhost:8000"
DEFAULT_SKILLS_PATH = Path("/app/skills")


def create_production_app() -> Starlette:
    """Build durable dependencies and wire the production ASGI application."""

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    audit_repository = SqliteAuditRepository(audit_db_path_from_environment())
    try:
        closed = audit_repository.bootstrap(recovered_at=datetime.now(UTC))
    except Exception:
        # Deliberately broad: any failure to open or reconcile the store is
        # the same operational fact, and the degraded posture above is the
        # same response to all of them.
        LOGGER.exception(
            "audit store at %s could not be opened; starting degraded and"
            " reporting unhealthy until it can be",
            audit_repository.path,
        )
    else:
        if closed:
            LOGGER.warning(
                "closed %d audit attempt(s) left open by a prior process as"
                " outcome_unknown",
                closed,
            )
        LOGGER.info("audit store ready at %s", audit_repository.path)

    session_secret_persistent = True
    try:
        session_secret = load_or_create_session_secret()
    except Exception:
        # A transient value lets the process expose a meaningful 503 instead
        # of crash-looping. Health remains false, so no traffic is routed and
        # no unstable session key is treated as production-ready.
        LOGGER.exception(
            "persistent session secret could not be loaded; starting degraded"
        )
        session_secret = secrets.token_urlsafe(48)
        session_secret_persistent = False
    else:
        LOGGER.info("persistent session secret is ready")

    audit_digest_key = None
    try:
        audit_digest_key = load_or_create_audit_digest_key()
    except Exception:
        # Without a durable digest key, identical arguments could never be
        # correlated across restarts, so the MCP surface is withheld and
        # readiness stays false instead of keying digests transiently.
        LOGGER.exception(
            "audit argument digest key could not be loaded; the MCP surface"
            " will not be built"
        )
    else:
        LOGGER.info("audit argument digest key is ready")

    packs = None
    pack_configuration_ready = True
    try:
        packs = load_backend_packs(operator_path=DEFAULT_OPERATOR_PACKS_PATH)
    except Exception:
        LOGGER.exception("backend packs could not be loaded; starting degraded")
        pack_configuration_ready = False

    runtime_repository = RuntimeRepository(
        config_db_path_from_environment(),
        credential_keyring_path_from_environment(),
        grantable_scopes=implemented_scopes(packs if packs is not None else {}),
        bootstrap_password_path=admin_bootstrap_path_from_environment(),
    )
    configuration_ready = pack_configuration_ready
    try:
        runtime_repository.bootstrap()
    except Exception:
        LOGGER.exception(
            "runtime configuration store could not be opened; starting degraded"
        )
        configuration_ready = False
    else:
        LOGGER.info(
            "runtime configuration store ready at %s",
            runtime_repository.database_path,
        )

    skills_path = Path(os.environ.get("SKILLS_PATH", str(DEFAULT_SKILLS_PATH)))
    skills = None
    try:
        skills = load_catalog(skills_path)
    except Exception:
        LOGGER.exception(
            "skills catalog at %s could not be loaded; starting degraded",
            skills_path,
        )
        configuration_ready = False

    public_base_url = os.environ.get("PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL)
    mcp_surfaces = None
    if configuration_ready and skills is not None and audit_digest_key is not None:
        try:
            mcp_surfaces = build_mcp_surfaces(
                runtime_repository=runtime_repository,
                audit_repository=audit_repository,
                skills=skills,
                digest_key=audit_digest_key,
                public_base_url=public_base_url,
                packs=packs,
            )
        except Exception:
            LOGGER.exception("authenticated MCP surface could not be built")

    return create_app(
        audit_repository=audit_repository,
        session_secret=session_secret,
        session_secret_persistent=session_secret_persistent,
        runtime_repository=(runtime_repository if configuration_ready else None),
        mcp_surfaces=mcp_surfaces,
        configuration_ready=configuration_ready,
        mcp_ready=mcp_surfaces is not None,
        session_https_only=public_base_url.lower().startswith("https://"),
    )
