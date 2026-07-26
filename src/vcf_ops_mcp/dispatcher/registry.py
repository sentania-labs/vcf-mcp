"""Validated tool registration and frozen outbound contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from vcf_ops_mcp.contracts import (
    REGISTRATION_SCHEMA_VERSION,
    REQUIRED_REGISTRATION_CORE,
    OutboundContract,
    ToolSpec,
)


class ToolRegistry:
    """Registry whose entries can only be invoked through generated wrappers."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._frozen = False

    def register(self, registration: Mapping[str, object]) -> ToolSpec:
        if self._frozen:
            raise RuntimeError("tool registry is frozen")

        missing = REQUIRED_REGISTRATION_CORE.difference(registration)
        if missing:
            raise ValueError(
                f"registration missing required core: {', '.join(sorted(missing))}"
            )
        if registration["schema_version"] != REGISTRATION_SCHEMA_VERSION:
            raise ValueError("unsupported registration schema version")

        extensions = {
            key: value
            for key, value in registration.items()
            if key not in REQUIRED_REGISTRATION_CORE
        }
        if any("." not in key for key in extensions):
            raise ValueError("extension keys must be family-qualified")

        name = registration["name"]
        capability = registration["capability"]
        key_scope = registration["key_scope"]
        outbound_contract = registration["outbound_contract"]
        handler = registration["audited_handler"]
        if not isinstance(name, str) or not name:
            raise ValueError("tool name must be a non-empty string")
        if capability is None or key_scope is None:
            raise ValueError("capability and key scope are required")
        if not isinstance(outbound_contract, OutboundContract):
            raise TypeError("outbound_contract must be an OutboundContract")
        if not callable(handler):
            raise TypeError("audited_handler must be callable")
        for field in (
            "target_policy",
            "argument_digest_policy",
            "projection",
        ):
            if not isinstance(registration[field], str) or not registration[field]:
                raise ValueError(f"{field} must be a non-empty string")
        if name in self._tools:
            raise ValueError(f"duplicate tool name: {name}")

        spec = ToolSpec(
            schema_version=REGISTRATION_SCHEMA_VERSION,
            name=name,
            capability=capability,  # type: ignore[arg-type]
            key_scope=key_scope,  # type: ignore[arg-type]
            target_policy=registration["target_policy"],  # type: ignore[arg-type]
            argument_digest_policy=registration[
                "argument_digest_policy"
            ],  # type: ignore[arg-type]
            projection=registration["projection"],  # type: ignore[arg-type]
            outbound_contract=outbound_contract,
            audited_handler=handler,
            extensions=extensions,
        )
        self._tools[name] = spec
        return spec

    def freeze(self) -> None:
        self._frozen = True

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self._tools.values())
