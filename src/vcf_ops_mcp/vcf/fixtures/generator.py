"""Generate synthetic fixtures from raw captures, by whitelist.

Decision 3 (3B). No raw captured byte is ever committed, and raw captures live
outside the repository worktree entirely. This generator reads one, projects an
explicit allowlist of response schema paths, substitutes deterministic
pseudonyms that preserve reference equality, and refuses anything it was not
told about.

**Why whitelist and not blocklist.** A scrubber that is 99 percent right is a
scrubber that leaks. A blocklist has to anticipate every shape of identifying
material that a future appliance version might add to a response; a whitelist
fails closed on a field nobody has looked at yet. So:

- An undeclared path raises ``UnknownSchemaPath``. It does not pass through and
  it is not dropped silently.
- A value whose class does not match its declaration raises
  ``UnknownValueClass``.
- The only values reproduced verbatim are those declared ``ENUM`` with an
  explicit allowed set, plus numbers and booleans. A value that is supposed to
  be vendor vocabulary but is not in the declared set is an error, never a
  quietly pseudonymized string.

**Reference equality is preserved.** A resource id appearing in an object and
again in a stats response must remain the same value or identity and link
parsing cannot be tested. One pseudonym map, keyed by the original value, is
shared across the whole document.

**The salt is random per run and is never recorded.** A fixed public salt would
make pseudonyms confirmable by brute force for a low-entropy input such as a
hostname, which would defeat the point. Tests pass an explicit salt to get
determinism; generation runs do not.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


GENERATOR_VERSION = "1.0.0"

# Timestamps are shifted onto a fixed base so a fixture does not carry the
# wall-clock moment of the capture while remaining internally consistent.
TIMESTAMP_BASE_MS = 1_700_000_000_000


class FixtureGenerationError(Exception):
    """Base of every refusal raised by the generator."""


class UnknownSchemaPath(FixtureGenerationError):
    """A path in the capture was not declared in the schema."""


class UnknownValueClass(FixtureGenerationError):
    """A value did not match the class its path declares."""


class ValueClass(StrEnum):
    OBJECT = "object"
    ARRAY = "array"
    DROP = "drop"
    ID = "id"
    NAME = "name"
    TEXT = "text"
    ENUM = "enum"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TIMESTAMP_MS = "timestamp_ms"


@dataclass(frozen=True, slots=True)
class Rule:
    value_class: ValueClass
    allowed: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.value_class is ValueClass.ENUM and not self.allowed:
            raise ValueError("an ENUM rule needs an explicit allowed set")


Schema = Mapping[str, Rule]


@dataclass(frozen=True, slots=True)
class FixtureMetadata:
    """Provenance every generated fixture carries."""

    generator_version: str
    source_api_version: str
    generation_date: str
    schema_digest: str

    def as_json(self) -> dict[str, str]:
        return {
            "generator_version": self.generator_version,
            "source_api_version": self.source_api_version,
            "generation_date": self.generation_date,
            "schema_digest": self.schema_digest,
        }


class Pseudonymizer:
    """Deterministic, reference-equality-preserving pseudonyms."""

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt if salt is not None else os.urandom(32)
        self._issued: dict[tuple[str, str], str] = {}

    def _digest(self, value_class: str, value: str) -> bytes:
        return hmac.new(
            self._salt, f"{value_class}\x00{value}".encode(), hashlib.sha256
        ).digest()

    def for_value(self, value_class: ValueClass, value: str) -> str:
        cached = self._issued.get((str(value_class), value))
        if cached is not None:
            return cached
        digest = self._digest(str(value_class), value).hex()
        if value_class is ValueClass.ID:
            # A UUID-shaped pseudonym, because callers parse these as ids.
            issued = (
                f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-"
                f"8{digest[17:20]}-{digest[20:32]}"
            )
        elif value_class is ValueClass.NAME:
            issued = f"synthetic-{digest[:12]}"
        else:
            issued = f"synthetic text {digest[:8]}"
        self._issued[(str(value_class), value)] = issued
        return issued


def schema_digest(schema: Schema) -> str:
    canonical = json.dumps(
        {
            path: [str(rule.value_class), sorted(rule.allowed)]
            for path, rule in sorted(schema.items())
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate(
    capture: Mapping[str, Any],
    schema: Schema,
    *,
    source_api_version: str,
    generation_date: str,
    salt: bytes | None = None,
) -> dict[str, Any]:
    """Project and pseudonymize one capture into a committable fixture.

    ``generation_date`` is supplied by the caller rather than read from the
    clock, so regenerating a fixture from the same capture is byte-identical
    apart from the salt-dependent pseudonyms.
    """

    pseudonymizer = Pseudonymizer(salt)
    document = _walk("", capture, schema, pseudonymizer)
    metadata = FixtureMetadata(
        generator_version=GENERATOR_VERSION,
        source_api_version=source_api_version,
        generation_date=generation_date,
        schema_digest=schema_digest(schema),
    )
    return {"metadata": metadata.as_json(), "document": document}


def _rule_for(path: str, schema: Schema) -> Rule:
    try:
        return schema[path]
    except KeyError:
        raise UnknownSchemaPath(
            f"the capture contains {path!r}, which the schema does not declare; "
            f"declare it or the fixture cannot be generated"
        ) from None


def _walk(path: str, value: Any, schema: Schema, names: Pseudonymizer) -> Any:
    rule = _rule_for(path, schema) if path else Rule(ValueClass.OBJECT)
    return _apply(path, rule, value, schema, names)


def _apply(
    path: str, rule: Rule, value: Any, schema: Schema, names: Pseudonymizer
) -> Any:
    if value is None:
        return None
    match rule.value_class:
        case ValueClass.OBJECT:
            if not isinstance(value, Mapping):
                raise UnknownValueClass(f"{path or 'the root'} is not an object")
            projected: dict[str, Any] = {}
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                child_rule = _rule_for(child_path, schema)
                if child_rule.value_class is ValueClass.DROP:
                    continue
                projected[key] = _apply(child_path, child_rule, child, schema, names)
            return projected
        case ValueClass.ARRAY:
            if not isinstance(value, list):
                raise UnknownValueClass(f"{path} is not an array")
            item_path = f"{path}[]"
            item_rule = _rule_for(item_path, schema)
            return [
                _apply(item_path, item_rule, item, schema, names) for item in value
            ]
        case ValueClass.ENUM:
            if not isinstance(value, str) or value not in rule.allowed:
                raise UnknownValueClass(
                    f"{path} carries a value outside its declared vocabulary; "
                    f"an undeclared value is refused, never pseudonymized"
                )
            return value
        case ValueClass.BOOLEAN:
            if not isinstance(value, bool):
                raise UnknownValueClass(f"{path} is not a boolean")
            return value
        case ValueClass.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise UnknownValueClass(f"{path} is not an integer")
            return value
        case ValueClass.NUMBER:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise UnknownValueClass(f"{path} is not a number")
            return value
        case ValueClass.TIMESTAMP_MS:
            if not isinstance(value, int) or isinstance(value, bool):
                raise UnknownValueClass(f"{path} is not an epoch-millisecond integer")
            if value == 0:
                return 0
            return TIMESTAMP_BASE_MS + (value % 86_400_000)
        case ValueClass.ID | ValueClass.NAME | ValueClass.TEXT:
            if not isinstance(value, str):
                raise UnknownValueClass(f"{path} is not a string")
            if not value:
                return ""
            return names.for_value(rule.value_class, value)
        case ValueClass.DROP:  # pragma: no cover, handled by the object arm
            raise UnknownValueClass(f"{path} is dropped and cannot be projected")
    raise UnknownValueClass(f"{path} has an unhandled value class")


def iter_strings(value: Any) -> Iterator[str]:
    """Every string scalar in a document, including object keys."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            yield key
            yield from iter_strings(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, str):
        yield value


def raw_tokens_in_output(
    capture: Mapping[str, Any], fixture: Mapping[str, Any], schema: Schema
) -> list[str]:
    """Every raw capture token that survived into the fixture.

    A token is any string scalar in the capture that is not an object key and
    not a value declared verbatim vocabulary by an ``ENUM`` rule. The proof
    test asserts this list is empty. Substring matching is deliberate: a leak
    that appears inside a longer string is still a leak.
    """

    allowed_verbatim = {
        value
        for rule in schema.values()
        if rule.value_class is ValueClass.ENUM
        for value in rule.allowed
    }
    capture_keys = set(_iter_keys(capture))
    serialized = json.dumps(fixture)
    leaked = []
    for token in _iter_scalar_strings(capture):
        if not token or token in allowed_verbatim or token in capture_keys:
            continue
        if token in serialized:
            leaked.append(token)
    return sorted(set(leaked))


def _iter_keys(value: Any) -> Iterator[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield key
            yield from _iter_keys(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_keys(item)


def _iter_scalar_strings(value: Any) -> Iterator[str]:
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _iter_scalar_strings(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_scalar_strings(item)
    elif isinstance(value, str):
        yield value


_LAB_MARKERS = (
    re.compile(r"sentania", re.IGNORECASE),
    re.compile(r"vcf-lab-", re.IGNORECASE),
    re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
)


def lab_markers_in(document: Mapping[str, Any] | Sequence[Any]) -> list[str]:
    """Backstop scan for lab-identifying material, not the primary control.

    The whitelist is the control. This exists so a mistake in a schema
    declaration is caught by something other than a human reading a diff.
    """

    serialized = json.dumps(document)
    return [
        pattern.pattern for pattern in _LAB_MARKERS if pattern.search(serialized)
    ]
