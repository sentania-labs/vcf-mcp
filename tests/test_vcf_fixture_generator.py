"""Tests for the synthetic fixture generator.

The capture below is synthetic but it is shaped like a real one and it is
deliberately full of the material that must never reach a fixture: the lab
domain, an RFC1918 address, a real-looking hostname, and an operator's note.
"""

from __future__ import annotations

import json
import unittest

from vcf_ops_mcp.vcf.fixtures import generator
from vcf_ops_mcp.vcf.fixtures.generator import (
    TIMESTAMP_BASE_MS,
    Rule,
    UnknownSchemaPath,
    UnknownValueClass,
    ValueClass,
    generate,
    lab_markers_in,
    raw_tokens_in_output,
)
from vcf_ops_mcp.vcf.fixtures.schemas import (
    ALERT_COLLECTION_SCHEMA,
    RESOURCE_COLLECTION_SCHEMA,
    STATS_SCHEMA,
)


SALT = b"deterministic-test-salt-not-a-secret"
RESOURCE_ID = "8f14e45f-ceea-467a-a8ba-1a0d6f4a0b11"
PEER_ID = "c9f0f895-fb98-4b41-9d0e-3a6d5b7c8e22"

CAPTURE = {
    "pageInfo": {"totalCount": 517, "page": 0, "pageSize": 2},
    "links": [{"href": "/suite-api/api/resources?page=1", "rel": "NEXT"}],
    "resourceList": [
        {
            "identifier": RESOURCE_ID,
            "creationTime": 1_760_000_123_456,
            "resourceKey": {
                "name": "vcf-lab-app-01.int.sentania.net",
                "adapterKindKey": "VMWARE",
                "resourceKindKey": "VirtualMachine",
                "resourceIdentifiers": [
                    {
                        "identifierType": {
                            "name": "VMEntityObjectID",
                            "dataType": "STRING",
                            "isPartOfUniqueness": True,
                        },
                        "value": "vm-4021",
                    }
                ],
            },
            "resourceStatusStates": [
                {
                    "adapterInstanceId": "6e7f8a90-1b2c-4d3e-8f01-234567890abc",
                    "resourceStatus": "DATA_RECEIVING",
                    "resourceState": "STARTED",
                    "statusMessage": "collecting from 10.20.30.40",
                }
            ],
            "resourceHealth": "GREEN",
            "resourceHealthValue": 100.0,
            "dtEnabled": True,
            "badges": [{"type": "RISK", "color": "GREEN", "score": 0.0}],
            "relatedResources": [PEER_ID],
            "links": [{"href": "/suite-api/api/resources/x", "rel": "SELF"}],
        },
        {
            "identifier": PEER_ID,
            "creationTime": 1_760_000_223_456,
            "resourceKey": {
                "name": "vcf-lab-db-02.int.sentania.net",
                "adapterKindKey": "VMWARE",
                "resourceKindKey": "HostSystem",
                "resourceIdentifiers": [],
            },
            "resourceStatusStates": [],
            "resourceHealth": "YELLOW",
            "resourceHealthValue": 74.5,
            "dtEnabled": False,
            "badges": [],
            "relatedResources": [],
            "links": [],
        },
    ],
}

STATS_CAPTURE = {
    "values": [
        {
            "resourceId": RESOURCE_ID,
            "stat-list": {
                "stat": [
                    {
                        "timestamps": [1_760_000_123_456, 1_760_000_423_456],
                        "statKey": {"key": "cpu|demandmhz"},
                        "rollUpType": "AVG",
                        "intervalUnit": {"quantifier": 5, "intervalType": "MINUTES"},
                        "data": [12.5, 13.25],
                    }
                ]
            },
        }
    ]
}


def build(capture=CAPTURE, schema=RESOURCE_COLLECTION_SCHEMA, salt=SALT) -> dict:
    return generate(
        capture,
        schema,
        source_api_version="VCF Operations 9.0.2.0",
        generation_date="2026-07-25",
        salt=salt,
    )


class ProofTests(unittest.TestCase):
    """The load-bearing test: no raw capture token reaches the output."""

    def test_no_raw_capture_token_appears_in_the_fixture(self) -> None:
        fixture = build()
        leaked = raw_tokens_in_output(CAPTURE, fixture, RESOURCE_COLLECTION_SCHEMA)
        self.assertEqual(leaked, [])

    def test_the_proof_test_fails_on_an_unscrubbed_document(self) -> None:
        """A proof that cannot fail is not proving anything.

        The negative control: hand the raw capture in as though it were the
        generated fixture and the check must report the leak.
        """

        leaked = raw_tokens_in_output(
            CAPTURE, {"document": CAPTURE}, RESOURCE_COLLECTION_SCHEMA
        )
        self.assertIn("vcf-lab-app-01.int.sentania.net", leaked)
        self.assertIn(RESOURCE_ID, leaked)

    def test_a_mis_declared_enum_is_caught_by_the_backstop_scanner(self) -> None:
        """The token check trusts ENUM declarations, so something else must not.

        Declaring lab-identifying material as vendor vocabulary is the one way
        to get a raw value into a fixture without tripping the token proof.
        That is what the backstop scan exists for.
        """

        leaky_schema = dict(RESOURCE_COLLECTION_SCHEMA)
        leaky_schema["resourceList[].resourceKey.name"] = Rule(
            ValueClass.ENUM, frozenset({"vcf-lab-app-01.int.sentania.net"})
        )
        capture = json.loads(json.dumps(CAPTURE))
        capture["resourceList"][1]["resourceKey"]["name"] = (
            "vcf-lab-app-01.int.sentania.net"
        )
        fixture = generate(
            capture,
            leaky_schema,
            source_api_version="VCF Operations 9.0.2.0",
            generation_date="2026-07-25",
            salt=SALT,
        )
        # Declared verbatim, so the token check exempts it, and the backstop
        # scanner is what catches the bad declaration.
        self.assertEqual(raw_tokens_in_output(capture, fixture, leaky_schema), [])
        self.assertTrue(lab_markers_in(fixture))

    def test_lab_markers_are_present_in_the_capture_and_absent_from_the_fixture(
        self,
    ) -> None:
        self.assertTrue(lab_markers_in(CAPTURE))
        self.assertEqual(lab_markers_in(build()), [])


class ReferenceEqualityTests(unittest.TestCase):
    def test_the_same_id_pseudonymizes_to_the_same_value_within_a_document(
        self,
    ) -> None:
        fixture = build()["document"]
        first, second = fixture["resourceList"]
        self.assertEqual(first["relatedResources"], [second["identifier"]])
        self.assertNotEqual(first["identifier"], second["identifier"])

    def test_the_same_id_pseudonymizes_consistently_across_documents(self) -> None:
        resources = build()["document"]
        stats = build(STATS_CAPTURE, STATS_SCHEMA)["document"]
        self.assertEqual(
            stats["values"][0]["resourceId"], resources["resourceList"][0]["identifier"]
        )

    def test_pseudonymous_ids_keep_a_uuid_shape(self) -> None:
        identifier = build()["document"]["resourceList"][0]["identifier"]
        self.assertRegex(
            identifier,
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$",
        )

    def test_regeneration_with_the_same_salt_is_byte_identical(self) -> None:
        self.assertEqual(json.dumps(build()), json.dumps(build()))

    def test_a_different_salt_produces_different_pseudonyms(self) -> None:
        other = build(salt=b"a-different-salt")
        self.assertNotEqual(
            build()["document"]["resourceList"][0]["identifier"],
            other["document"]["resourceList"][0]["identifier"],
        )
        # Structure is unchanged, only the pseudonyms move.
        self.assertEqual(
            sorted(build()["document"]["resourceList"][0]),
            sorted(other["document"]["resourceList"][0]),
        )

    def test_the_default_salt_is_random_and_unrecorded(self) -> None:
        first = generate(
            CAPTURE,
            RESOURCE_COLLECTION_SCHEMA,
            source_api_version="VCF Operations 9.0.2.0",
            generation_date="2026-07-25",
        )
        second = generate(
            CAPTURE,
            RESOURCE_COLLECTION_SCHEMA,
            source_api_version="VCF Operations 9.0.2.0",
            generation_date="2026-07-25",
        )
        self.assertNotEqual(
            first["document"]["resourceList"][0]["identifier"],
            second["document"]["resourceList"][0]["identifier"],
        )
        self.assertNotIn("salt", json.dumps(first))


class RefusalTests(unittest.TestCase):
    def test_an_undeclared_path_is_refused(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["resourceList"][0]["newFieldFromAnUpgrade"] = "anything"
        with self.assertRaises(UnknownSchemaPath) as caught:
            build(capture)
        self.assertIn("newFieldFromAnUpgrade", str(caught.exception))

    def test_an_undeclared_top_level_path_is_refused(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["extra"] = {"nested": 1}
        with self.assertRaises(UnknownSchemaPath):
            build(capture)

    def test_a_value_outside_a_declared_vocabulary_is_refused(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["resourceList"][0]["resourceHealth"] = "MAUVE"
        with self.assertRaises(UnknownValueClass) as caught:
            build(capture)
        self.assertIn("never pseudonymized", str(caught.exception))

    def test_a_value_of_the_wrong_class_is_refused(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["pageInfo"]["totalCount"] = "517"
        with self.assertRaises(UnknownValueClass):
            build(capture)

    def test_an_object_where_an_array_is_declared_is_refused(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["resourceList"] = {"not": "an array"}
        with self.assertRaises(UnknownValueClass):
            build(capture)

    def test_an_enum_rule_requires_an_explicit_allowed_set(self) -> None:
        with self.assertRaises(ValueError):
            Rule(ValueClass.ENUM)


class ProjectionTests(unittest.TestCase):
    def test_dropped_paths_are_absent_rather_than_emptied(self) -> None:
        document = build()["document"]
        self.assertNotIn("links", document)
        for item in document["resourceList"]:
            self.assertNotIn("links", item)

    def test_vendor_vocabulary_survives_verbatim(self) -> None:
        item = build()["document"]["resourceList"][0]
        self.assertEqual(item["resourceKey"]["adapterKindKey"], "VMWARE")
        self.assertEqual(item["resourceKey"]["resourceKindKey"], "VirtualMachine")
        self.assertEqual(item["resourceHealth"], "GREEN")

    def test_numbers_and_booleans_survive(self) -> None:
        document = build()["document"]
        self.assertEqual(document["pageInfo"]["totalCount"], 517)
        self.assertEqual(document["resourceList"][0]["resourceHealthValue"], 100.0)
        self.assertIs(document["resourceList"][0]["dtEnabled"], True)

    def test_timestamps_are_shifted_onto_a_fixed_base(self) -> None:
        created = build()["document"]["resourceList"][0]["creationTime"]
        self.assertNotEqual(created, CAPTURE["resourceList"][0]["creationTime"])
        self.assertGreaterEqual(created, TIMESTAMP_BASE_MS)
        self.assertLess(created, TIMESTAMP_BASE_MS + 86_400_000)

    def test_a_zero_timestamp_stays_zero(self) -> None:
        capture = {
            "pageInfo": {"totalCount": 1, "page": 0, "pageSize": 1},
            "alerts": [
                {
                    "alertId": RESOURCE_ID,
                    "resourceId": PEER_ID,
                    "alertLevel": "CRITICAL",
                    "type": "17",
                    "subType": "19",
                    "status": "ACTIVE",
                    "startTimeUTC": 1_760_000_123_456,
                    "cancelTimeUTC": 0,
                    "updateTimeUTC": 1_760_000_223_456,
                    "suspendUntilTimeUTC": 0,
                    "controlState": "OPEN",
                    "alertDefinitionId": "AlertDefinition-VMWARE-x",
                    "alertDefinitionName": "Host is down",
                    "alertImpact": "HEALTH",
                    "links": [],
                }
            ],
        }
        alert = build(capture, ALERT_COLLECTION_SCHEMA)["document"]["alerts"][0]
        self.assertEqual(alert["cancelTimeUTC"], 0)
        self.assertNotEqual(alert["updateTimeUTC"], 1_760_000_223_456)

    def test_null_values_pass_through_as_null(self) -> None:
        capture = json.loads(json.dumps(CAPTURE))
        capture["resourceList"][0]["resourceKey"]["name"] = None
        self.assertIsNone(
            build(capture)["document"]["resourceList"][0]["resourceKey"]["name"]
        )


class MetadataTests(unittest.TestCase):
    def test_every_fixture_carries_its_provenance(self) -> None:
        metadata = build()["metadata"]
        self.assertEqual(metadata["generator_version"], generator.GENERATOR_VERSION)
        self.assertEqual(metadata["source_api_version"], "VCF Operations 9.0.2.0")
        self.assertEqual(metadata["generation_date"], "2026-07-25")
        self.assertRegex(metadata["schema_digest"], r"^[0-9a-f]{64}$")

    def test_the_schema_digest_moves_when_the_schema_moves(self) -> None:
        changed = dict(RESOURCE_COLLECTION_SCHEMA)
        changed["resourceList[].newField"] = Rule(ValueClass.TEXT)
        self.assertNotEqual(
            generator.schema_digest(RESOURCE_COLLECTION_SCHEMA),
            generator.schema_digest(changed),
        )


if __name__ == "__main__":
    unittest.main()
