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
    check_local_links,
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



    def test_there_is_no_url_target(self):
        with self.assertRaises(TypeError):
            base_url(production=False, url="https://x.example/")
        with self.assertRaises(TypeError):
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


class LocalLinksTests(unittest.TestCase):
    """check_local_links refuses an instance that advertises another host."""

    def getter(self, status=200, payload=None):
        self.calls = []

        def get(url, **kw):
            self.calls.append((url, kw))
            resp = types.SimpleNamespace(status_code=status)
            resp.json = lambda: payload
            resp.text = str(payload)
            return resp

        return get

    def advertising(self, host):
        return {"links": {"self": f"{host}api/records?page=1&size=1"}}

    def test_an_instance_advertising_itself_passes(self):
        get = self.getter(payload=self.advertising(LOCAL))
        check_local_links(get)

    def test_the_request_goes_to_the_local_instance_unverified(self):
        get = self.getter(payload=self.advertising(LOCAL))
        check_local_links(get)
        (url, kw), = self.calls
        self.assertTrue(url.startswith(LOCAL + "api/records"), url)
        self.assertIs(kw.get("verify", True), False)

    def test_an_instance_advertising_production_is_refused(self):
        get = self.getter(payload=self.advertising(PRODUCTION))
        with self.assertRaises(ValueError) as caught:
            check_local_links(get)
        message = str(caught.exception)
        self.assertIn("authors.library.caltech.edu", message)
        self.assertIn("127.0.0.1:5000", message)
        self.assertIn("SITE_UI_URL", message)
        self.assertIn("SITE_API_URL", message)

    def test_a_look_alike_host_is_refused(self):
        # a prefix match on the host would accept this
        get = self.getter(payload=self.advertising("https://127.0.0.1:50001/"))
        with self.assertRaises(ValueError):
            check_local_links(get)

    def test_an_error_status_is_refused(self):
        # the payload alone would pass, so only the status can refuse it
        get = self.getter(status=500, payload=self.advertising(LOCAL))
        with self.assertRaises(ValueError):
            check_local_links(get)

    def test_a_reply_without_links_is_refused(self):
        with self.assertRaises(ValueError):
            check_local_links(self.getter(payload={}))

    def test_an_unreachable_instance_is_refused(self):
        def get(url, **kw):
            raise ConnectionError("refused")

        with self.assertRaises(ValueError) as caught:
            check_local_links(get)
        self.assertIn("127.0.0.1:5000", str(caught.exception))


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



    def test_the_url_has_no_double_slash_before_api(self):
        self.check_doi("10.1/x", production=False, local=True)
        self.assertNotIn("//api", self.url())

    def test_check_doi_takes_no_url_argument(self):
        with self.assertRaises(TypeError):
            self.check_doi("10.1/x", production=False, url="https://x.example/")

    def test_token_header_still_sent(self):
        self.check_doi("10.1/x", production=False, local=True, token="T")
        self.assertEqual(self.kw()["headers"], {"Authorization": "Bearer T"})

    def test_found_and_not_found(self):
        self.assertFalse(self.check_doi("10.1/x", production=False, local=True))


if __name__ == "__main__":
    unittest.main()
