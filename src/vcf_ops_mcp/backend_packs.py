"""Validated, data-only backend definition packs loaded at startup.

Official built-ins and an optional operator directory are loaded through the
same validator, then frozen before MCP composition. Pack signing, feed install,
rollback, and trust-root refresh remain deliberately deferred.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from vcf_ops_mcp.contracts import (
    BackendKind,
    Capability,
    CapabilityName,
    HttpMethod,
)


DEFAULT_PACKS_PATH = Path(__file__).with_name("packs")
DEFAULT_OPERATOR_PACKS_PATH = Path("/data/backend-packs")
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
LEGACY_TOOL_COUNT_EXEMPTIONS = frozenset({BackendKind.VCENTER})


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
    caps: dict[str, int]
    projection_keys: frozenset[str]
    digest: str


def load_backend_packs(
    path: Path = DEFAULT_PACKS_PATH,
    *,
    operator_path: Path | None = None,
) -> dict[BackendKind, BackendPack]:
    packs = _load_pack_directory(path, source_kind="official")
    missing = BUILTIN_BACKENDS - frozenset(packs)
    if missing:
        names = ", ".join(sorted(kind.value for kind in missing))
        raise ValueError(f"required built-in backend packs are missing: {names}")
    selected_operator_path = operator_path
    if selected_operator_path is not None and selected_operator_path.exists():
        operator_packs = _load_pack_directory(
            selected_operator_path, source_kind="operator"
        )
        overlap = frozenset(packs) & frozenset(operator_packs)
        if overlap:
            names = ", ".join(sorted(kind.value for kind in overlap))
            raise ValueError(f"operator packs cannot replace built-ins: {names}")
        packs.update(operator_packs)
    return packs


def _load_pack_directory(
    path: Path,
    *,
    source_kind: str,
) -> dict[BackendKind, BackendPack]:
    packs: dict[BackendKind, BackendPack] = {}
    for pack_path in sorted(path.glob("*.json")):
        raw = pack_path.read_bytes()
        try:
            document = json.loads(raw)
            if document.get("schema_version") != 1:
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
            if (
                backend not in LEGACY_TOOL_COUNT_EXEMPTIONS
                and len(tools) < MINIMUM_TOOL_COUNT
            ):
                raise ValueError(
                    f"backend packs require at least {MINIMUM_TOOL_COUNT} tools"
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
            declared_source_kind = str(document.get("source_kind", source_kind))
            if declared_source_kind != source_kind:
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
                unsigned=bool(document.get("unsigned", True)),
                tools=tools,
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
        default_location = (
            "path" if "{" + wire_name + "}" in path else "argument"
        )
        parsed_arguments.append(
            PackArgument(
                name=str(argument["name"]),
                type=str(argument["type"]),
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
    response_keys = frozenset(
        str(value) for value in document.get("response_keys", projection_keys)
    )
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
