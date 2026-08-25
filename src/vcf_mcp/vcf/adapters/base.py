"""What a read adapter is, and what it must declare to be registrable.

An adapter is the only thing tool code can reach the network through. It binds
one capability, one frozen outbound contract, one projection version, and one
handler. It cannot express a method, path, query parameter, or body key it did
not declare.

The registration mapping produced here fills every key of
``contracts.REQUIRED_REGISTRATION_CORE`` except ``audited_handler``, which the
dispatcher supplies when it wraps the handler. A handler that never reaches the
dispatcher is not an unaudited tool, it is a tool that does not exist.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from vcf_mcp.contracts import (
    REGISTRATION_SCHEMA_VERSION,
    CapabilityName,
    JsonObject,
    ToolHandler,
)
from vcf_mcp.vcf.outbound import OutboundAllowlist, ReadContract


# Every Phase 1 adapter reads through a registered target, and every argument
# digest is the HMAC of canonical JSON (SPEC section 8).
TARGET_POLICY_REQUIRED = "target_required"
ARGUMENT_DIGEST_HMAC_CANONICAL_JSON = "hmac_sha256_canonical_json"


@dataclass(frozen=True, slots=True)
class ReadAdapter:
    """One registrable read tool."""

    tool_name: str
    capability: CapabilityName
    read_contract: ReadContract
    handler: Callable[..., Awaitable[JsonObject]]
    summary: str
    target_policy: str = TARGET_POLICY_REQUIRED
    argument_digest_policy: str = ARGUMENT_DIGEST_HMAC_CANONICAL_JSON

    @property
    def key_scope(self) -> CapabilityName:
        # Phase 1 has one scope per capability. They are separate fields in the
        # registration core because Phase 2 may grant a narrower key scope than
        # the capability the tool needs.
        return self.capability

    @property
    def projection_version(self) -> str:
        return self.read_contract.projection_version

    def registration_mapping(self, *, audited_handler: ToolHandler) -> dict[str, Any]:
        """The open versioned registration record for this adapter."""

        return {
            "schema_version": REGISTRATION_SCHEMA_VERSION,
            "name": self.tool_name,
            "capability": self.capability,
            "key_scope": self.key_scope,
            "target_policy": self.target_policy,
            "argument_digest_policy": self.argument_digest_policy,
            "projection": self.projection_version,
            "outbound_contract": self.read_contract.contract,
            "audited_handler": audited_handler,
            "adapter.summary": self.summary,
            **self.read_contract.registration_extensions(),
        }


def build_allowlist(adapters: tuple[ReadAdapter, ...]) -> OutboundAllowlist:
    """Freeze the union of every registered adapter's outbound contract."""

    return OutboundAllowlist([adapter.read_contract for adapter in adapters])
