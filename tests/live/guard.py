"""Mechanical guards for the live tier.

Two independent controls, because the live tier is the one place in this
project where a test touches a real appliance:

1. **A host allowlist that cannot contain the prod FQDN.** Asserted at import
   time, not at use time, so a future edit that adds prod fails the moment the
   module loads.
2. **An httpx event hook over the enumerated read set.** Any method or path
   outside the frozen outbound allowlist, plus the two auth paths, raises
   before the request is sent. A live test that tries to mutate fails as a test
   error rather than as a mutation.
"""

from __future__ import annotations

import re

import httpx

from vcf_ops_mcp.vcf.adapters import READ_ALLOWLIST
from vcf_ops_mcp.vcf.client import (
    SUITE_API_ROOT,
    TOKEN_ACQUIRE_PATH,
    TOKEN_RELEASE_PATH,
)


# The lab's production appliance. It is never a live-tier target, and per the
# constitution it may only ever be registered read-only until Scott personally
# flips it. The policy slice owns the authoritative prod FQDN list used for
# is_prod evaluation; this copy exists so the live tier's guard does not depend
# on that slice landing first, and the two are reconciled at integration.
PROD_FQDN = "vcf-lab-operations.int.sentania.net"

LIVE_HOST_ALLOWLIST = frozenset({"vcf-lab-operations-devel.int.sentania.net"})

assert PROD_FQDN not in LIVE_HOST_ALLOWLIST, (
    "the prod appliance cannot be a live-tier target"
)


class OutsideTheReadSet(AssertionError):
    """Raised when a live test attempts a request outside the read set."""


def _template_pattern(template: str) -> re.Pattern[str]:
    escaped = re.escape(template)
    # Path parameters were escaped as \{name\}; accept one safe segment.
    escaped = re.sub(r"\\\{[a-z_]+\\\}", r"[A-Za-z0-9][A-Za-z0-9._:-]*", escaped)
    return re.compile(rf"^{escaped}$")


def read_set_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Every (method, path pattern) a live test is permitted to issue."""

    permitted = [
        (str(method), _template_pattern(template))
        for method, template in READ_ALLOWLIST.frozen_pairs
    ]
    permitted.append(("POST", _template_pattern(TOKEN_ACQUIRE_PATH)))
    permitted.append(("POST", _template_pattern(TOKEN_RELEASE_PATH)))
    # Unauthenticated registration surface, per SPEC section 13.
    permitted.append(("GET", _template_pattern("/api/auth/sources")))
    permitted.append(("GET", _template_pattern("/api/versions/current")))
    return permitted


async def refuse_outside_the_read_set(request: httpx.Request) -> None:
    """httpx request event hook. Raises rather than sending."""

    path = request.url.path.removeprefix(SUITE_API_ROOT)
    for method, pattern in read_set_patterns():
        if request.method == method and pattern.match(path):
            return
    raise OutsideTheReadSet(
        f"{request.method} {path} is outside the enumerated read set; the live "
        f"tier refuses it before it is sent"
    )


def assert_host_is_permitted(fqdn: str) -> str:
    """Refuse any host that is not on the allowlist."""

    normalized = fqdn.strip().rstrip(".").lower()
    if normalized == PROD_FQDN:
        raise AssertionError(
            "the prod appliance is never a live-tier target under any flag"
        )
    if normalized not in LIVE_HOST_ALLOWLIST:
        raise AssertionError(
            f"{normalized!r} is not on the live-tier host allowlist"
        )
    return normalized
