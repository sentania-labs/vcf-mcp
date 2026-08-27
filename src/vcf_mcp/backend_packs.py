"""Validated, data-only backend definition packs loaded at startup.

Official built-ins and a trust-verified operator directory are loaded through
the same validator, then frozen before MCP composition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from string import Formatter

from vcf_mcp.contracts import (
    BackendKind,
    Capability,
    CapabilityName,
    HttpMethod,
)


DEFAULT_PACKS_PATH = Path(__file__).with_name("packs")
DEFAULT_OPERATOR_PACKS_PATH = Path("/data/backend-packs/active")
SUPPORTED_AUTH_SCHEMES = frozenset(
    {
        "basic",
        "bearer_token",
        "ops_bearer",
        "ops_exchange",
        "ops_token",
        "sddc_token",
        "vcenter_session",
    }
)
BUILTIN_BACKENDS = frozenset(
    {
        BackendKind.OPS,
        BackendKind.VCENTER,
        BackendKind.NSX,
        BackendKind.SDDC_MANAGER,
        BackendKind.OPS_NETWORKS,
        BackendKind.FLEET_LCM,
        BackendKind.SDDC_LCM,
        BackendKind.LOG_MANAGEMENT,
        BackendKind.VSAN_DP,
    }
)
MINIMUM_TOOL_COUNT = 19
SUPPORTED_ARGUMENT_TYPES = frozenset(
    {
        "str",
        "str?",
        "int",
        "int?",
        "bool",
        "bool?",
        "list[str]",
        "list[str]?",
    }
)


@dataclass(frozen=True, slots=True)
class PackArgument:
    name: str
    type: str
    required: bool = False
    default: object | None = None
    description: str = ""
    location: str = "argument"
    wire_name: str | None = None


@dataclass(frozen=True, slots=True)
class PackTool:
    name: str
    summary: str
    capability: CapabilityName
    method: HttpMethod
    path: str
    query: frozenset[str]
    body: frozenset[str]
    projection: str
    arguments: tuple[PackArgument, ...]
    response_keys: frozenset[str]
    fixed_query: dict[str, object]
    body_template: object | None


@dataclass(frozen=True, slots=True)
class PackVerificationProbe:
    """Cheapest read-only request a pack offers for credential verification."""

    tool: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class BackendPack:
    pack_id: str
    version: str
    backend: BackendKind
    endpoint: str
    product: str
    auth_scheme: str
    api_root: str
    source: str
    unsigned: bool
    tools: tuple[PackTool, ...]
    verification_probe: PackVerificationProbe
    caps: dict[str, int]
    projection_keys: frozenset[str]
    digest: str


def load_backend_packs(
    path: Path = DEFAULT_PACKS_PATH,
    *,
    operator_path: Path | None = None,
    verified_operator_digests: Mapping[BackendKind, str | None] | None = None,
) -> dict[BackendKind, BackendPack]:
    packs = _load_pack_directory(path, source_kind="official")
    missing = BUILTIN_BACKENDS - frozenset(packs)
    if missing:
        names = ", ".join(sorted(kind.value for kind in missing))
        raise ValueError(f"required built-in backend packs are missing: {names}")
    selected_operator_path = operator_path
    if selected_operator_path is not None and selected_operator_path.exists():
        operator_packs = _load_pack_directory(selected_operator_path, source_kind=None)
        overlap = frozenset(packs) & frozenset(operator_packs)
        if overlap and verified_operator_digests is None:
            names = ", ".join(sorted(kind.value for kind in overlap))
            raise ValueError(f"operator packs cannot replace built-ins: {names}")
        if verified_operator_digests is not None:
            for backend, pack in operator_packs.items():
                if backend not in verified_operator_digests:
                    raise ValueError(
                        f"operator pack {backend.value} has no trust decision"
                    )
                verified = verified_operator_digests[backend]
                if verified is not None and verified != pack.digest:
                    raise ValueError(
                        f"operator pack {backend.value} changed after verification"
                    )
                operator_packs[backend] = replace(pack, unsigned=verified is None)
        packs.update(operator_packs)
    return packs


def _load_pack_directory(
    path: Path,
    *,
    source_kind: str | None,
) -> dict[BackendKind, BackendPack]:
    packs: dict[BackendKind, BackendPack] = {}
    for pack_path in sorted(path.glob("*.json")):
        if pack_path.name.endswith(".sigstore.json"):
            continue
        raw = pack_path.read_bytes()
        try:
            document = json.loads(raw)
            if document.get("schema_version") != 2:
                raise ValueError("unsupported pack schema version")
            backend = BackendKind(document["backend"])
            auth_scheme = str(document["auth_scheme"])
            if auth_scheme not in SUPPORTED_AUTH_SCHEMES:
                raise ValueError(f"unsupported auth scheme {auth_scheme!r}")
            projection_keys = frozenset(
                str(value) for value in document.get("projection_keys", [])
            )
            tools = tuple(
                _tool_from_document(item, projection_keys=projection_keys)
                for item in document["tools"]
            )
            names = [tool.name for tool in tools]
            if len(names) != len(set(names)) or not names:
                raise ValueError("pack tool names must be non-empty and unique")
            if len(tools) < MINIMUM_TOOL_COUNT:
                raise ValueError(
                    f"backend packs require at least {MINIMUM_TOOL_COUNT} tools"
                )
            probe_document = document["verification_probe"]
            probe = PackVerificationProbe(
                tool=str(probe_document["tool"]),
                arguments={
                    str(key): value
                    for key, value in probe_document.get("arguments", {}).items()
                },
            )
            probe_tool = next(
                (tool for tool in tools if tool.name == probe.tool), None
            )
            if probe_tool is None:
                raise ValueError("verification probe must name a declared tool")
            if probe_tool.method is not HttpMethod.GET:
                raise ValueError("verification probe must use a read-only GET tool")
            expected_arguments = {
                argument.name for argument in probe_tool.arguments
            }
            required_arguments = {
                argument.name
                for argument in probe_tool.arguments
                if argument.required
            }
            supplied_arguments = set(probe.arguments)
            if not required_arguments.issubset(supplied_arguments):
                raise ValueError(
                    "verification probe is missing required tool arguments"
                )
            if not supplied_arguments.issubset(expected_arguments):
                raise ValueError(
                    "verification probe arguments exceed the declared tool schema"
                )
            endpoint = str(document["endpoint"])
            if endpoint != backend.value:
                raise ValueError("pack endpoint must match backend name")
            api_root = str(document["api_root"])
            if api_root and (
                not api_root.startswith("/")
                or ".." in api_root
                or "://" in api_root
            ):
                raise ValueError("pack API root must be an absolute plain path")
            declared_source_kind = str(document.get("source_kind", source_kind or "operator"))
            if source_kind is not None and declared_source_kind != source_kind:
                raise ValueError(
                    f"pack source kind must be {source_kind!r} in this directory"
                )
            pack = BackendPack(
                pack_id=str(document["id"]),
                version=str(document["version"]),
                backend=backend,
                endpoint=endpoint,
                product=str(document["product"]),
                auth_scheme=auth_scheme,
                api_root=api_root.rstrip("/"),
                source=str(document["source"]),
                unsigned=(
                    False
                    if source_kind == "official"
                    else bool(document.get("unsigned", True))
                ),
                tools=tools,
                verification_probe=probe,
                caps={
                    str(key): int(value)
                    for key, value in document.get("caps", {}).items()
                },
                projection_keys=projection_keys,
                digest=hashlib.sha256(raw).hexdigest(),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid backend pack {pack_path.name}: {exc}") from exc
        if backend in packs:
            raise ValueError(f"duplicate backend pack for {backend.value}")
        packs[backend] = pack
    return packs


def _tool_from_document(
    document: dict[str, object],
    *,
    projection_keys: frozenset[str],
) -> PackTool:
    path = str(document["path"])
    if not path.startswith("/") or ".." in path or "://" in path:
        raise ValueError("tool paths must be absolute plain paths")
    parsed_arguments: list[PackArgument] = []
    for argument in document.get("arguments", []):
        wire_name = str(argument.get("wire_name", argument["name"]))
        argument_type = str(argument["type"])
        if argument_type not in SUPPORTED_ARGUMENT_TYPES:
            raise ValueError(f"unsupported argument type {argument_type!r} in pack")
        default_location = (
            "path" if "{" + wire_name + "}" in path else "argument"
        )
        parsed_arguments.append(
            PackArgument(
                name=str(argument["name"]),
                type=argument_type,
                required=bool(argument.get("required", False)),
                default=argument.get("default"),
                description=str(argument.get("description", "")),
                location=str(argument.get("location", default_location)),
                wire_name=wire_name,
            )
        )
    arguments = tuple(parsed_arguments)
    argument_names = [argument.name for argument in arguments]
    if len(argument_names) != len(set(argument_names)):
        raise ValueError("tool argument names must be unique")
    locations = {argument.location for argument in arguments}
    if not locations.issubset({"argument", "path", "query", "body"}):
        raise ValueError("tool argument locations are invalid")
    for argument in arguments:
        if argument.location == "path" and not argument.required:
            raise ValueError("path arguments must be required")
    expected_path_names = {
        field_name
        for _, field_name, _, _ in Formatter().parse(path)
        if field_name is not None
    }
    declared_path_names = {
        str(argument.wire_name)
        for argument in arguments
        if argument.location == "path"
    }
    if expected_path_names != declared_path_names:
        raise ValueError("path arguments must exactly match the path template")
    query = frozenset(str(value) for value in document.get("query", []))
    body = frozenset(str(value) for value in document.get("body", []))
    fixed_query = {
        str(key): value for key, value in document.get("fixed_query", {}).items()
    }
    declared_query_names = {
        str(argument.wire_name)
        for argument in arguments
        if argument.location == "query"
    } | set(fixed_query)
    if not declared_query_names.issubset(query):
        raise ValueError("query arguments must be permitted by the tool contract")
    body_template = document.get("body_template")
    declared_body_names = {
        str(argument.wire_name)
        for argument in arguments
        if argument.location == "body"
    }
    if body_template is not None:
        if not isinstance(body_template, dict):
            raise ValueError("body template must be a JSON object")
        declared_body_names |= set(str(key) for key in body_template)
        unknown_template_arguments = _template_arguments(body_template) - set(
            argument_names
        )
        if unknown_template_arguments:
            raise ValueError("body template names an unknown argument")
    if not declared_body_names.issubset(body):
        raise ValueError("body arguments must be permitted by the tool contract")
    if "response_keys" not in document:
        raise ValueError(
            "every tool requires its own response projection allowlist"
        )
    response_keys = frozenset(str(value) for value in document["response_keys"])
    if not response_keys:
        raise ValueError("pack tools require a non-empty response projection allowlist")
    return PackTool(
        name=str(document["name"]),
        summary=str(document["summary"]),
        capability=Capability(str(document["capability"])),
        method=HttpMethod(str(document["method"])),
        path=path,
        query=query,
        body=body,
        projection=str(document["projection"]),
        arguments=arguments,
        response_keys=response_keys,
        fixed_query=fixed_query,
        body_template=body_template,
    )


def _template_arguments(value: object) -> set[str]:
    if isinstance(value, dict):
        marker = value.get("$argument")
        if marker is not None and len(value) == 1:
            return {str(marker)}
        found: set[str] = set()
        for nested in value.values():
            found.update(_template_arguments(nested))
        return found
    if isinstance(value, list):
        found = set()
        for nested in value:
            found.update(_template_arguments(nested))
        return found
    return set()
