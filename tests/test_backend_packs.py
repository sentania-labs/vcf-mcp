from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcf_mcp.backend_packs import DEFAULT_PACKS_PATH, load_backend_packs
from vcf_mcp.contracts import BackendKind


REMAINING_OFFICIAL = frozenset(
    {
        BackendKind.NSX,
        BackendKind.SDDC_MANAGER,
        BackendKind.OPS_NETWORKS,
        BackendKind.FLEET_LCM,
        BackendKind.SDDC_LCM,
        BackendKind.LOG_MANAGEMENT,
        BackendKind.VSAN_DP,
    }
)

VCENTER_CONTRACTS = {
    "list_vcenter_vms": ("/api/vcenter/vm", {"vms", "names", "folders", "datacenters", "hosts", "clusters", "resource_pools", "power_states"}),
    "get_vcenter_vm": ("/api/vcenter/vm/{vm}", set()),
    "list_vcenter_hosts": ("/api/vcenter/host", {"hosts", "names", "folders", "datacenters", "clusters", "connection_states", "standalone"}),
    "list_vcenter_clusters": ("/api/vcenter/cluster", {"clusters", "names", "folders", "datacenters"}),
    "get_vcenter_cluster": ("/api/vcenter/cluster/{cluster}", set()),
    "list_vcenter_datacenters": ("/api/vcenter/datacenter", {"datacenters", "names", "folders"}),
    "get_vcenter_datacenter": ("/api/vcenter/datacenter/{datacenter}", set()),
    "list_vcenter_datastores": ("/api/vcenter/datastore", {"datastores", "names", "types", "folders", "datacenters"}),
    "get_vcenter_datastore": ("/api/vcenter/datastore/{datastore}", set()),
    "list_vcenter_resource_pools": ("/api/vcenter/resource-pool", {"resource_pools", "names", "parent_resource_pools", "datacenters", "hosts", "clusters"}),
    "get_vcenter_resource_pool": ("/api/vcenter/resource-pool/{resourcePool}", set()),
    "list_vcenter_folders": ("/api/vcenter/folder", {"folders", "names", "parent_folders", "datacenters"}),
    "list_vcenter_networks": ("/api/vcenter/network", {"networks", "names", "types", "folders", "datacenters"}),
    "list_vcenter_storage_policies": ("/api/vcenter/storage/policies", {"policies"}),
    "list_vcenter_content_libraries": ("/api/content/library", set()),
    "get_vcenter_content_library": ("/api/content/library/{libraryId}", set()),
    "list_vcenter_content_library_items": ("/api/content/library/item", {"library_id"}),
    "get_vcenter_content_library_item": ("/api/content/library/item/{libraryItemId}", set()),
    "get_vcenter_session": ("/api/session", set()),
}

SENSITIVE_RESPONSE_TOOLS = {
    BackendKind.LOG_MANAGEMENT: {
        "list_log_agent_secrets": {"value", "secret", "password", "token"},
    },
    BackendKind.FLEET_LCM: {
        "get_fleet_component_config": {"password"},
    },
    BackendKind.SDDC_LCM: {
        "get_sddc_lcm_component_config": {"password"},
    },
    BackendKind.OPS_NETWORKS: {
        "get_networks_vcenter": {"credentials", "password"},
        "get_networks_nsx_manager": {
            "credentials",
            "password",
            "client_private_key",
        },
    },
    BackendKind.VCENTER: {
        "get_vcenter_content_library": {
            "password",
            "current_password",
        },
    },
}


def test_remaining_official_backends_ship_as_nineteen_tool_packs() -> None:
    packs = load_backend_packs()

    assert REMAINING_OFFICIAL.issubset(packs)
    for backend in REMAINING_OFFICIAL:
        pack = packs[backend]
        assert len(pack.tools) == 19
        assert pack.endpoint == backend.value
        assert "vmware/vcf-api-specs" in pack.source
        assert "NiranEC77" not in pack.source
        assert all(tool.response_keys for tool in pack.tools)


def test_all_nine_builtin_products_ship_exactly_nineteen_tools() -> None:
    packs = load_backend_packs()

    assert len(packs) == 9
    assert all(len(pack.tools) == 19 for pack in packs.values())


def test_vcenter_pack_freezes_nineteen_distinct_official_get_contracts() -> None:
    pack = load_backend_packs()[BackendKind.VCENTER]

    assert len(VCENTER_CONTRACTS) == 19
    assert {tool.name for tool in pack.tools} == set(VCENTER_CONTRACTS)
    assert "vmware/vcf-api-specs" in pack.source
    assert "vcenter.yaml" in pack.source
    for tool in pack.tools:
        expected_path, expected_query = VCENTER_CONTRACTS[tool.name]
        assert tool.method == "GET"
        assert tool.path == expected_path
        assert tool.query == expected_query


def test_operator_pack_loads_alongside_official_set(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator-packs"
    operator_path.mkdir()
    document = _operator_pack(BackendKind.AVI)
    (operator_path / "avi.json").write_text(json.dumps(document))

    packs = load_backend_packs(operator_path=operator_path)

    assert set(load_backend_packs()).issubset(packs)
    assert packs[BackendKind.AVI].source == "operator-supplied fixture"
    assert len(packs[BackendKind.AVI].tools) == 19


def test_operator_pack_cannot_replace_an_official_backend(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator-packs"
    operator_path.mkdir()
    document = _operator_pack(BackendKind.NSX)
    (operator_path / "nsx.json").write_text(json.dumps(document))

    with pytest.raises(ValueError, match="cannot replace built-ins"):
        load_backend_packs(operator_path=operator_path)


def test_operator_pack_cannot_compress_below_nineteen_tools(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator-packs"
    operator_path.mkdir()
    document = _operator_pack(BackendKind.IDENTITY_BROKER)
    document["tools"] = document["tools"][:18]
    (operator_path / "identity.json").write_text(json.dumps(document))

    with pytest.raises(ValueError, match="at least 19 tools"):
        load_backend_packs(operator_path=operator_path)


def test_every_tool_requires_its_own_response_allowlist(tmp_path: Path) -> None:
    operator_path = tmp_path / "operator-packs"
    operator_path.mkdir()
    document = _operator_pack(BackendKind.IDENTITY_BROKER)
    del document["tools"][0]["response_keys"]
    (operator_path / "identity.json").write_text(json.dumps(document))

    with pytest.raises(ValueError, match="its own response projection allowlist"):
        load_backend_packs(operator_path=operator_path)


def test_operator_pack_rejects_unsupported_argument_types_at_load(
    tmp_path: Path,
) -> None:
    operator_path = tmp_path / "operator-packs"
    operator_path.mkdir()
    document = _operator_pack(BackendKind.AUTOMATION)
    document["tools"][0]["arguments"] = [
        {"name": "mistyped", "type": "string", "default": None}
    ]
    (operator_path / "automation.json").write_text(json.dumps(document))

    with pytest.raises(ValueError, match="unsupported argument type 'string'"):
        load_backend_packs(operator_path=operator_path)


def test_sensitive_response_tools_have_narrow_tool_specific_allowlists() -> None:
    packs = load_backend_packs()

    for backend, tool_fields in SENSITIVE_RESPONSE_TOOLS.items():
        pack = packs[backend]
        tools = {tool.name: tool for tool in pack.tools}
        for tool_name, sensitive_fields in tool_fields.items():
            response_keys = tools[tool_name].response_keys
            assert response_keys != pack.projection_keys
            assert response_keys.isdisjoint(sensitive_fields)


def test_every_builtin_file_is_consumed_by_the_validated_loader() -> None:
    filenames = {path.stem for path in DEFAULT_PACKS_PATH.glob("*.json")}
    backends = {backend.value for backend in load_backend_packs()}
    assert filenames == backends


def _operator_pack(backend: BackendKind) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": f"fixture.{backend.value}",
        "version": "1.0.0",
        "backend": backend.value,
        "endpoint": backend.value,
        "product": f"Fixture {backend.value}",
        "auth_scheme": "basic",
        "api_root": "/api",
        "source": "operator-supplied fixture",
        "source_kind": "operator",
        "unsigned": True,
        "projection_keys": ["id", "name", "items", "count"],
        "tools": [
            {
                "name": f"get_fixture_{index}",
                "summary": f"Get fixture {index}.",
                "capability": "read:inventory",
                "method": "GET",
                "path": f"/fixtures/{index}",
                "projection": "fixture.v1",
                "response_keys": ["id", "name", "items", "count"],
            }
            for index in range(19)
        ],
    }
