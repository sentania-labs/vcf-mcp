"""Every Phase 1 read adapter, and the frozen outbound allowlist they imply.

``READ_ADAPTERS`` is the whole read surface. The dispatcher slice walks it,
wraps each handler, and registers the wrapper. ``READ_ALLOWLIST`` is the frozen
union the transport enforces, so a call the registry never saw cannot be
issued.

The skills family (``list_skills``, ``get_skill``) and the targets family are
not here: neither reaches a VCF appliance, so neither is an adapter in this
layer.
"""

from __future__ import annotations

from vcf_ops_mcp.vcf.adapters import alerts, inventory, metrics, reports
from vcf_ops_mcp.vcf.adapters.base import ReadAdapter, build_allowlist


READ_ADAPTERS: tuple[ReadAdapter, ...] = (
    *inventory.ADAPTERS,
    *metrics.ADAPTERS,
    *alerts.ADAPTERS,
    *reports.ADAPTERS,
)

READ_ALLOWLIST = build_allowlist(READ_ADAPTERS)

ADAPTERS_BY_TOOL_NAME: dict[str, ReadAdapter] = {
    adapter.tool_name: adapter for adapter in READ_ADAPTERS
}

__all__ = [
    "ADAPTERS_BY_TOOL_NAME",
    "READ_ADAPTERS",
    "READ_ALLOWLIST",
    "ReadAdapter",
    "alerts",
    "build_allowlist",
    "inventory",
    "metrics",
    "reports",
]
