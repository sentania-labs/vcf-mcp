"""Declared schema paths for the captures this slice turns into fixtures.

Every path a capture may contain is enumerated here with its value class. An
appliance upgrade that adds a field makes generation fail loudly on the new
path, which is the intended behavior: a human decides whether the new field is
vendor vocabulary, an identifier, or lab-identifying material. Nothing new
passes through by default.

The enum sets are vendor vocabulary reproduced verbatim, and they are the only
strings from a capture that survive into a fixture unchanged.
"""

from __future__ import annotations

from vcf_ops_mcp.vcf.fixtures.generator import Rule, Schema, ValueClass


def _enum(*values: str) -> Rule:
    return Rule(ValueClass.ENUM, frozenset(values))


_OBJECT = Rule(ValueClass.OBJECT)
_ARRAY = Rule(ValueClass.ARRAY)
_DROP = Rule(ValueClass.DROP)
_ID = Rule(ValueClass.ID)
_NAME = Rule(ValueClass.NAME)
_TEXT = Rule(ValueClass.TEXT)
_INT = Rule(ValueClass.INTEGER)
_NUMBER = Rule(ValueClass.NUMBER)
_BOOL = Rule(ValueClass.BOOLEAN)
_TIMESTAMP = Rule(ValueClass.TIMESTAMP_MS)

ADAPTER_KINDS = _enum(
    "VMWARE",
    "VirtualAndPhysicalSANAdapter",
    "Container",
    "CLOUD_HEALTH_ADAPTER",
    "SDDCHealthAdapter",
    "VCFAdapter",
)
RESOURCE_KINDS = _enum(
    "VirtualMachine",
    "HostSystem",
    "ClusterComputeResource",
    "Datastore",
    "Datacenter",
    "vSphere World",
    "ResourcePool",
    "VMFolder",
)
HEALTH = _enum("GREEN", "YELLOW", "ORANGE", "RED", "GREY")
RESOURCE_STATUS = _enum(
    "DATA_RECEIVING", "NOT_EXISTING", "NO_PARENT_MONITORING", "UNKNOWN", "NONE"
)
RESOURCE_STATE = _enum("STARTED", "STOPPED", "NOT_EXISTING", "UNKNOWN", "NONE")
BADGE_TYPES = _enum(
    "RISK", "EFFICIENCY", "HEALTH", "WORKLOAD", "ANOMALY", "FAULT", "CAPACITY_REMAINING"
)
IDENTIFIER_TYPES = _enum(
    "VMEntityObjectID",
    "VMEntityName",
    "VMEntityInstanceUUID",
    "VMEntityVCID",
    "entityName",
    "moid",
)
CRITICALITY = _enum("CRITICAL", "IMMEDIATE", "WARNING", "INFORMATION", "AUTO", "NONE")
ALERT_STATUS = _enum("ACTIVE", "CANCELED", "INACTIVE", "NEW", "SUSPENDED")
CONTROL_STATE = _enum("OPEN", "ASSIGNED", "SUPPRESSED")
ALERT_IMPACT = _enum("HEALTH", "RISK", "EFFICIENCY", "BADGE")


PAGED_ENVELOPE: dict[str, Rule] = {
    "pageInfo": _OBJECT,
    "pageInfo.totalCount": _INT,
    "pageInfo.page": _INT,
    "pageInfo.pageSize": _INT,
    "links": _DROP,
}


def _prefixed(prefix: str, paths: dict[str, Rule]) -> dict[str, Rule]:
    return {f"{prefix}{path}": rule for path, rule in paths.items()}


_RESOURCE_ITEM: dict[str, Rule] = {
    "": _OBJECT,
    ".identifier": _ID,
    ".creationTime": _TIMESTAMP,
    ".resourceKey": _OBJECT,
    ".resourceKey.name": _NAME,
    ".resourceKey.adapterKindKey": ADAPTER_KINDS,
    ".resourceKey.resourceKindKey": RESOURCE_KINDS,
    ".resourceKey.resourceIdentifiers": _ARRAY,
    ".resourceKey.resourceIdentifiers[]": _OBJECT,
    ".resourceKey.resourceIdentifiers[].identifierType": _OBJECT,
    ".resourceKey.resourceIdentifiers[].identifierType.name": IDENTIFIER_TYPES,
    ".resourceKey.resourceIdentifiers[].identifierType.dataType": _enum(
        "STRING", "INTEGER", "DOUBLE"
    ),
    ".resourceKey.resourceIdentifiers[].identifierType.isPartOfUniqueness": _BOOL,
    ".resourceKey.resourceIdentifiers[].value": _ID,
    ".resourceStatusStates": _ARRAY,
    ".resourceStatusStates[]": _OBJECT,
    ".resourceStatusStates[].adapterInstanceId": _ID,
    ".resourceStatusStates[].resourceStatus": RESOURCE_STATUS,
    ".resourceStatusStates[].resourceState": RESOURCE_STATE,
    ".resourceStatusStates[].statusMessage": _TEXT,
    ".resourceHealth": HEALTH,
    ".resourceHealthValue": _NUMBER,
    ".dtEnabled": _BOOL,
    ".badges": _ARRAY,
    ".badges[]": _OBJECT,
    ".badges[].type": BADGE_TYPES,
    ".badges[].color": HEALTH,
    ".badges[].score": _NUMBER,
    ".relatedResources": _ARRAY,
    ".relatedResources[]": _ID,
    ".links": _DROP,
}

RESOURCE_COLLECTION_SCHEMA: Schema = {
    **PAGED_ENVELOPE,
    "resourceList": _ARRAY,
    **_prefixed("resourceList[]", _RESOURCE_ITEM),
}

RESOURCE_DETAIL_SCHEMA: Schema = _prefixed("", _RESOURCE_ITEM)

ALERT_COLLECTION_SCHEMA: Schema = {
    **PAGED_ENVELOPE,
    "alerts": _ARRAY,
    "alerts[]": _OBJECT,
    "alerts[].alertId": _ID,
    "alerts[].resourceId": _ID,
    "alerts[].alertLevel": CRITICALITY,
    "alerts[].type": _TEXT,
    "alerts[].subType": _TEXT,
    "alerts[].status": ALERT_STATUS,
    "alerts[].startTimeUTC": _TIMESTAMP,
    "alerts[].cancelTimeUTC": _TIMESTAMP,
    "alerts[].updateTimeUTC": _TIMESTAMP,
    "alerts[].suspendUntilTimeUTC": _TIMESTAMP,
    "alerts[].controlState": CONTROL_STATE,
    "alerts[].alertDefinitionId": _ID,
    "alerts[].alertDefinitionName": _NAME,
    "alerts[].alertImpact": ALERT_IMPACT,
    "alerts[].links": _DROP,
}

STATS_SCHEMA: Schema = {
    "values": _ARRAY,
    "values[]": _OBJECT,
    "values[].resourceId": _ID,
    "values[].stat-list": _OBJECT,
    "values[].stat-list.stat": _ARRAY,
    "values[].stat-list.stat[]": _OBJECT,
    "values[].stat-list.stat[].timestamps": _ARRAY,
    "values[].stat-list.stat[].timestamps[]": _TIMESTAMP,
    "values[].stat-list.stat[].statKey": _OBJECT,
    "values[].stat-list.stat[].statKey.key": _TEXT,
    "values[].stat-list.stat[].rollUpType": _enum(
        "AVG", "MIN", "MAX", "SUM", "LATEST", "COUNT"
    ),
    "values[].stat-list.stat[].intervalUnit": _OBJECT,
    "values[].stat-list.stat[].intervalUnit.quantifier": _INT,
    "values[].stat-list.stat[].intervalUnit.intervalType": _enum(
        "SECONDS", "MINUTES", "HOURS", "DAYS", "WEEKS", "MONTHS", "YEARS"
    ),
    "values[].stat-list.stat[].data": _ARRAY,
    "values[].stat-list.stat[].data[]": _NUMBER,
}

__all__ = [
    "ALERT_COLLECTION_SCHEMA",
    "RESOURCE_COLLECTION_SCHEMA",
    "RESOURCE_DETAIL_SCHEMA",
    "STATS_SCHEMA",
]
