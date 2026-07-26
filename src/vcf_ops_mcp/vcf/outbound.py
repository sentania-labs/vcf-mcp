"""The frozen outbound allowlist: method, path template, and parameter names.

SPEC section 4.2. Every adapter declares the exact HTTP method, path template,
and permitted query parameter names it may use. The registry freezes the union
and the transport refuses anything outside it, before any socket work.

The parameter half is not decoration, and this was re-measured against DEVEL on
2026-07-25:

- ``GET /api/resources?identifier=<uuid>`` (a plausible misspelling of a real
  filter) is silently ignored and returns all 517 resources in 1,115,211 bytes
  with a 200, correctly shaped and correctly paginated, at the wrong scope.
- ``GET /api/alerts?activeOnly=true``, ``?alertCriticality=CRITICAL`` and
  ``?status=ACTIVE`` are all silently ignored: totalCount stays 1216. The same
  filters supplied in the body of ``POST /api/alerts/query`` do work (40 and
  703 respectively). An adapter that guesses the GET form gets the unfiltered
  collection and no error.

No fixture test can catch that, because a mock answers whatever URL it is
handed. The live tier is where the allowlist is validated against reality.

A body-key allowlist is carried here as well, because on this API the effective
filters for several families live in a POST body rather than the query string.
That is an additive, family-qualified extension to the shared registration
mapping (``vcf.permitted_body_keys``) per the extension rule in
``contracts.py``, not an edit to the shared triple.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from vcf_ops_mcp.contracts import HttpMethod, OutboundContract
from vcf_ops_mcp.vcf.errors import OutboundContractViolation


_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

# Identifiers this API actually uses: UUIDs, adapter kind keys such as
# "VMWARE", and composite definition ids such as
# "SymptomDefinition-VMWARE-VMCPUContentionInfo". Anything else, including any
# form of slash, dot segment, percent escape, or whitespace, is refused.
_SAFE_PATH_VALUE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")

# The read set. A method outside this tuple cannot be expressed by an adapter,
# and there is no mutation transport in Phase 1 to express it with.
READ_METHODS: frozenset[HttpMethod] = frozenset({HttpMethod.GET, HttpMethod.POST})


@dataclass(frozen=True, slots=True)
class ReadContract:
    """One adapter's declared outbound surface.

    ``contract`` is the shared ``(method, path_template, query parameters)``
    triple from ``contracts.py``. ``permitted_body_keys`` is the additive
    family-qualified extension described in this module's docstring.
    """

    name: str
    contract: OutboundContract
    projection_version: str
    permitted_body_keys: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.contract.method not in READ_METHODS:
            raise ValueError(f"{self.name}: method outside the read set")
        if not self.contract.path_template.startswith("/"):
            raise ValueError(f"{self.name}: path template must be absolute")
        if self.permitted_body_keys and self.contract.method is not HttpMethod.POST:
            raise ValueError(f"{self.name}: body keys declared on a GET contract")

    @property
    def path_parameter_names(self) -> frozenset[str]:
        return frozenset(_PLACEHOLDER.findall(self.contract.path_template))

    def registration_extensions(self) -> dict[str, object]:
        """The family-qualified fields this contract adds at registration."""

        return {
            "vcf.permitted_body_keys": sorted(self.permitted_body_keys),
            "vcf.projection_version": self.projection_version,
        }


class OutboundAllowlist:
    """The frozen union of every registered read contract."""

    def __init__(self, contracts: Sequence[ReadContract]) -> None:
        by_name: dict[str, ReadContract] = {}
        for contract in contracts:
            if contract.name in by_name:
                raise ValueError(f"duplicate read contract name {contract.name!r}")
            by_name[contract.name] = contract
        self._by_name = by_name
        self._frozen = frozenset(
            (c.contract.method, c.contract.path_template) for c in contracts
        )

    def __contains__(self, contract: ReadContract) -> bool:
        registered = self._by_name.get(contract.name)
        return registered is not None and registered == contract

    def get(self, name: str) -> ReadContract:
        try:
            return self._by_name[name]
        except KeyError:
            raise OutboundContractViolation(
                f"no read contract named {name!r} is registered"
            ) from None

    @property
    def frozen_pairs(self) -> frozenset[tuple[HttpMethod, str]]:
        """Every (method, path template) pair the transport will ever issue."""

        return self._frozen

    def check(self, contract: ReadContract) -> None:
        if contract not in self:
            raise OutboundContractViolation(
                f"read contract {contract.name!r} is not in the frozen allowlist"
            )


def render_path(
    contract: ReadContract, path_parameters: Mapping[str, str] | None = None
) -> str:
    """Render a path template, refusing anything that could leave the template.

    The rendered path is checked back against the template so a parameter value
    can never introduce a new segment, a dot segment, or a query string.
    """

    supplied = dict(path_parameters or {})
    expected = contract.path_parameter_names
    if set(supplied) != set(expected):
        raise OutboundContractViolation(
            f"{contract.name}: path parameters {sorted(supplied)} do not match "
            f"the template's {sorted(expected)}"
        )
    for key, value in supplied.items():
        if not isinstance(value, str) or not _SAFE_PATH_VALUE.fullmatch(value):
            raise OutboundContractViolation(
                f"{contract.name}: path parameter {key!r} is not a safe identifier"
            )
    rendered = _PLACEHOLDER.sub(lambda m: supplied[m.group(1)], contract.contract.path_template)
    if rendered.count("/") != contract.contract.path_template.count("/"):
        raise OutboundContractViolation(
            f"{contract.name}: rendered path changed its segment count"
        )
    if ".." in rendered or "?" in rendered or "#" in rendered or "//" in rendered:
        raise OutboundContractViolation(
            f"{contract.name}: rendered path is not a plain resource path"
        )
    return rendered


def check_query(
    contract: ReadContract, query: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Refuse any query parameter name outside the contract's allowlist."""

    supplied = dict(query or {})
    permitted = contract.contract.permitted_query_parameters
    unknown = sorted(set(supplied) - set(permitted))
    if unknown:
        raise OutboundContractViolation(
            f"{contract.name}: query parameters {unknown} are not permitted; "
            f"this appliance silently ignores unknown parameters and returns "
            f"the unfiltered collection with a 200"
        )
    return {key: value for key, value in supplied.items() if value is not None}


def check_body(
    contract: ReadContract, body: Mapping[str, object] | None = None
) -> dict[str, object] | None:
    """Refuse any request body key outside the contract's allowlist."""

    if body is None:
        return None
    if contract.contract.method is not HttpMethod.POST:
        raise OutboundContractViolation(
            f"{contract.name}: a body cannot be sent on a GET contract"
        )
    unknown = sorted(set(body) - set(contract.permitted_body_keys))
    if unknown:
        raise OutboundContractViolation(
            f"{contract.name}: body keys {unknown} are not permitted"
        )
    return {key: value for key, value in body.items() if value is not None}
