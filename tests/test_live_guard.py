"""Tier 1 tests for the live tier's own guards. No network.

The live tier is opt-in and never runs in CI, so its guards would otherwise be
the only untested safety control in this slice. These run everywhere.
"""

from __future__ import annotations

import asyncio
import unittest

import httpx

from tests.live.guard import (
    LIVE_HOST_ALLOWLIST,
    PROD_FQDN,
    OutsideTheReadSet,
    assert_host_is_permitted,
    refuse_outside_the_read_set,
)


DEVEL = "vcf-lab-operations-devel.int.sentania.net"


def hook(method: str, path: str) -> None:
    request = httpx.Request(method, f"https://{DEVEL}/suite-api{path}")
    asyncio.run(refuse_outside_the_read_set(request))


class HostAllowlistTests(unittest.TestCase):
    def test_the_prod_fqdn_is_not_on_the_allowlist(self) -> None:
        self.assertNotIn(PROD_FQDN, LIVE_HOST_ALLOWLIST)

    def test_prod_is_refused_by_name(self) -> None:
        for spelling in (PROD_FQDN, PROD_FQDN.upper(), f"{PROD_FQDN}.", f" {PROD_FQDN} "):
            with self.subTest(spelling=spelling):
                with self.assertRaises(AssertionError):
                    assert_host_is_permitted(spelling)

    def test_an_unlisted_host_is_refused(self) -> None:
        for host in ("example.com", "vcf-lab-operations-devel.int.sentania.net.evil"):
            with self.subTest(host=host):
                with self.assertRaises(AssertionError):
                    assert_host_is_permitted(host)

    def test_devel_is_permitted_in_any_reasonable_spelling(self) -> None:
        for spelling in (DEVEL, DEVEL.upper(), f"{DEVEL}."):
            self.assertEqual(assert_host_is_permitted(spelling), DEVEL)


class ReadSetHookTests(unittest.TestCase):
    def test_declared_read_paths_pass(self) -> None:
        for method, path in (
            ("GET", "/api/resources"),
            ("GET", "/api/resources/11111111-1111-4111-8111-111111111111"),
            ("POST", "/api/alerts/query"),
            ("POST", "/api/resources/stats/query"),
            ("GET", "/api/adapterkinds/VMWARE/resourcekinds"),
            ("POST", "/api/auth/token/acquire"),
            ("GET", "/api/auth/sources"),
        ):
            with self.subTest(path=path):
                hook(method, path)

    def test_a_mutation_path_is_refused_before_it_is_sent(self) -> None:
        for method, path in (
            ("POST", "/api/actions/someAction"),
            ("POST", "/api/events/query"),
            ("DELETE", "/api/resources/11111111-1111-4111-8111-111111111111"),
            ("PUT", "/api/resources"),
            ("PATCH", "/api/alerts/query"),
        ):
            with self.subTest(path=path):
                with self.assertRaises(OutsideTheReadSet):
                    hook(method, path)

    def test_a_read_path_with_the_wrong_verb_is_refused(self) -> None:
        with self.assertRaises(OutsideTheReadSet):
            hook("POST", "/api/resources")

    def test_a_path_parameter_cannot_widen_the_pattern(self) -> None:
        with self.assertRaises(OutsideTheReadSet):
            hook("GET", "/api/resources/abc/relationships")


if __name__ == "__main__":
    unittest.main()
