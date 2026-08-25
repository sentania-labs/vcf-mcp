"""Validated, data-only backend definition packs loaded at startup.

The prototype ships two unsigned built-in packs. Pack signing, feed install,
rollback, and trust-root refresh are deliberately deferred. The loader accepts
any directory so the later signed install path does not require a new content
model.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from vcf_ops_mcp.contracts import BackendKind, CapabilityName, HttpMethod


DEFAULT_PACKS_PATH = Path(__file__).with_name("packs")
SUPPORTED_AUTH_SCHEMES = frozenset({"ops_token", "vcenter_session"})


@dataclass(frozen=True, slots=True)
class PackArgument:
    name: str
    type: str
    required: bool = False
    default: object | None = None
    description: str = ""


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
    digest: str


def load_backend_packs(
    path: Path = DEFAULT_PACKS_PATH,
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
            tools = tuple(_tool_from_document(item) for item in document["tools"])
            names = [tool.name for tool in tools]
            if len(names) != len(set(names)) or not names:
                raise ValueError("pack tool names must be non-empty and unique")
            endpoint = str(document["endpoint"])
            if endpoint != backend.value:
                raise ValueError("prototype endpoint must match backend name")
            pack = BackendPack(
                pack_id=str(document["id"]),
                version=str(document["version"]),
                backend=backend,
                endpoint=endpoint,
                product=str(document["product"]),
                auth_scheme=auth_scheme,
                api_root=str(document["api_root"]),
                source=str(document["source"]),
                unsigned=bool(document.get("unsigned", True)),
                tools=tools,
                caps={
                    str(key): int(value)
                    for key, value in document.get("caps", {}).items()
                },
                digest=hashlib.sha256(raw).hexdigest(),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid backend pack {pack_path.name}: {exc}") from exc
        if backend in packs:
            raise ValueError(f"duplicate backend pack for {backend.value}")
        packs[backend] = pack
    required = frozenset({BackendKind.OPS, BackendKind.VCENTER})
    if frozenset(packs) != required:
        missing = ", ".join(sorted(kind.value for kind in required - frozenset(packs)))
        raise ValueError(f"required built-in backend packs are missing: {missing}")
    return packs


def _tool_from_document(document: dict[str, object]) -> PackTool:
    path = str(document["path"])
    if not path.startswith("/") or ".." in path:
        raise ValueError("tool paths must be absolute plain paths")
    arguments = tuple(
        PackArgument(
            name=str(argument["name"]),
            type=str(argument["type"]),
            required=bool(argument.get("required", False)),
            default=argument.get("default"),
            description=str(argument.get("description", "")),
        )
        for argument in document.get("arguments", [])
    )
    return PackTool(
        name=str(document["name"]),
        summary=str(document["summary"]),
        capability=str(document["capability"]),
        method=HttpMethod(str(document["method"])),
        path=path,
        query=frozenset(str(value) for value in document.get("query", [])),
        body=frozenset(str(value) for value in document.get("body", [])),
        projection=str(document["projection"]),
        arguments=arguments,
    )
