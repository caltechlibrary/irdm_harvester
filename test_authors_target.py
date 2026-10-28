"""Tests for authors_target and for check_doi's use of it.

Run with: python3 -m unittest test_authors_target
requests is stubbed, so no network and no third-party modules are needed.
"""

import importlib
import sys
import types
import unittest
from unittest import mock

import authors_target
from authors_target import (
    COMMUNITY_ENV,
    base_url,
    community_id,
    tls_verify,
)

PRODUCTION = "https://authors.library.caltech.edu/"
DEV = "https://authors.caltechlibrary.dev/"
LOCAL = "https://127.0.0.1:5000/"
PROD_COMMUNITY = "aedd135f-227e-4fdf-9476-5b3fd011bac6"
DEV_COMMUNITY = "fb980d43-af44-48bc-bdd6-f785653038b8"


class BaseUrlTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        import os

        os.environ.pop(COMMUNITY_ENV, None)
        os.environ.pop("AUTHORS_LOCAL_URL", None)

    def test_production(self):
        self.assertEqual(base_url(production=True), PRODUCTION)

    def test_dev_when_not_production(self):
        self.assertEqual(base_url(production=False), DEV)

    def test_local_is_the_loopback_default(self):
        self.assertEqual(base_url(production=False, local=True), LOCAL)

    def test_local_wins_over_production(self):
        self.assertEqual(base_url(production=True, local=True), LOCAL)

    def test_local_ignores_a_url_in_the_environment(self):
        # caltechdata_api's local=True always writes to 127.0.0.1:5000, so a
        # different read address would split one run across two hosts
        import os

        os.environ["AUTHORS_LOCAL_URL"] = "https://localhost:8443"
        self.assertEqual(base_url(production=False, local=True), LOCAL)

    def test_url_names_any_target_and_gets_one_trailing_slash(self):
        for given in ("https://authors.example.org", "https://authors.example.org/"):
            self.assertEqual(
                base_url(production=False, url=given), "https://authors.example.org/"
            )

    def test_url_wins_over_production_and_local(self):
        self.assertEqual(
            base_url(production=True, local=True, url="https://x.example/"),
            "https://x.example/",
        )

    def test_blank_url_is_ignored(self):
        self.assertEqual(base_url(production=False, url="  "), DEV)

    def test_tls_verify_is_off_only_for_local(self):
        self.assertTrue(tls_verify(local=False))
        self.assertFalse(tls_verify(local=True))


class CommunityTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        import os

        os.environ.pop(COMMUNITY_ENV, None)

    def test_production_and_dev_ids_are_unchanged(self):
        self.assertEqual(community_id(production=True), PROD_COMMUNITY)
        self.assertEqual(community_id(production=False), DEV_COMMUNITY)

    def test_local_reads_the_environment(self):
        import os

        os.environ[COMMUNITY_ENV] = "abc-123"
        self.assertEqual(community_id(production=False, local=True), "abc-123")

    def test_url_also_reads_the_environment(self):
        import os

        os.environ[COMMUNITY_ENV] = "def-456"
        self.assertEqual(community_id(production=False, url="https://x.example/"), "def-456")

    def test_url_without_the_environment_is_an_error(self):
        with self.assertRaises(ValueError):
            community_id(production=False, url="https://x.example/")

    def test_local_without_the_environment_is_an_error_naming_it(self):
        with self.assertRaises(ValueError) as cm:
            community_id(production=False, local=True)
        self.assertIn(COMMUNITY_ENV, str(cm.exception))

    def test_local_with_a_blank_environment_is_an_error(self):
        import os

        os.environ[COMMUNITY_ENV] = "  "
        with self.assertRaises(ValueError):
            community_id(production=False, local=True)

    def test_local_does_not_silently_fall_back_to_a_real_community(self):
        # the dev and production ids must never be used for a local target
        try:
            got = community_id(production=True, local=True)
        except ValueError:
            return
        self.assertNotIn(got, (PROD_COMMUNITY, DEV_COMMUNITY))


class CheckDoiTests(unittest.TestCase):
    """check_doi asks the right host, and skips TLS checks only for local."""

    def setUp(self):
        self.calls = []
        outer = self

        def get(url, **kw):
            outer.calls.append((url, kw))
            resp = types.SimpleNamespace(status_code=200)
            resp.json = lambda: {"hits": {"total": 0}}
            return resp

        stub = types.ModuleType("requests")
        stub.get = get
        patcher = mock.patch.dict(sys.modules, {"requests": stub})
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("check_doi", None)
        self.check_doi = importlib.import_module("check_doi").check_doi
        self.addCleanup(lambda: sys.modules.pop("check_doi", None))
        import os

        patcher2 = mock.patch.dict("os.environ", clear=False)
        patcher2.start()
        self.addCleanup(patcher2.stop)
        os.environ.pop("AUTHORS_LOCAL_URL", None)

    def url(self):
        return self.calls[-1][0]

    def kw(self):
        return self.calls[-1][1]

    def test_production(self):
        self.check_doi("10.1/x", production=True)
        self.assertTrue(self.url().startswith(PRODUCTION + "api/records?"))
        self.assertTrue(self.kw()["verify"])

    def test_dev(self):
        self.check_doi("10.1/x", production=False)
        self.assertTrue(self.url().startswith(DEV + "api/records?"))
        self.assertTrue(self.kw()["verify"])

    def test_local(self):
        self.check_doi("10.1/x", production=False, local=True)
        self.assertTrue(self.url().startswith(LOCAL + "api/records?"))
        self.assertIs(self.kw()["verify"], False)

    def test_url_target_keeps_tls_verification_on(self):
        self.check_doi("10.1/x", production=False, url="https://authors.example.org")
        self.assertTrue(self.url().startswith("https://authors.example.org/api/records?"))
        self.assertTrue(self.kw()["verify"])

    def test_url_with_local_turns_verification_off(self):
        self.check_doi("10.1/x", production=False, local=True, url="https://localhost:8443")
        self.assertTrue(self.url().startswith("https://localhost:8443/api/records?"))
        self.assertIs(self.kw()["verify"], False)

    def test_the_url_has_no_double_slash_before_api(self):
        self.check_doi("10.1/x", production=False, local=True)
        self.assertNotIn("//api", self.url())

    def test_token_header_still_sent(self):
        self.check_doi("10.1/x", production=False, local=True, token="T")
        self.assertEqual(self.kw()["headers"], {"Authorization": "Bearer T"})

    def test_found_and_not_found(self):
        self.assertFalse(self.check_doi("10.1/x", production=False, local=True))


if __name__ == "__main__":
    unittest.main()
