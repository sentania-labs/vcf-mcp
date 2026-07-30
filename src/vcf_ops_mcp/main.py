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
from datetime import UTC, datetime

from starlette.applications import Starlette

from vcf_ops_mcp.app import create_app
from vcf_ops_mcp.audit import (
    SqliteAuditRepository,
    audit_db_path_from_environment,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_LOG_LEVEL = "INFO"


def create_production_app() -> Starlette:
    """Build the audit store, reconcile it, and wire the ASGI application."""

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    repository = SqliteAuditRepository(audit_db_path_from_environment())
    try:
        closed = repository.bootstrap(recovered_at=datetime.now(UTC))
    except Exception:
        # Deliberately broad: any failure to open or reconcile the store is
        # the same operational fact, and the degraded posture above is the
        # same response to all of them.
        LOGGER.exception(
            "audit store at %s could not be opened; starting degraded and"
            " reporting unhealthy until it can be",
            repository.path,
        )
    else:
        if closed:
            LOGGER.warning(
                "closed %d audit attempt(s) left open by a prior process as"
                " outcome_unknown",
                closed,
            )
        LOGGER.info("audit store ready at %s", repository.path)

    return create_app(audit_repository=repository)
