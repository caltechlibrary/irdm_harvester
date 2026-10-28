"""Tests for authors_target.install_host_guard.

A CaltechAUTHORS built from production's configuration advertises links on
authors.library.caltech.edu, and caltechdata_api follows those links. The guard
must make sure a run aimed at another target never sends a request to the
production or dev authors host, and must leave every other host alone.

Run with: python3 -m unittest test_host_guard
requests is stubbed, so no network is used.
"""

import sys
import types
import unittest
from unittest import mock

import authors_target

TARGET = "https://127.0.0.1:5000/"
PRODUCTION = "https://authors.library.caltech.edu"
DEV = "https://authors.caltechlibrary.dev"


def stub_requests():
    sent = []

    class Session:
        def request(self, method, url, *args, **kwargs):
            sent.append((method, url, kwargs))
            return "response"

    sessions = types.ModuleType("requests.sessions")
    sessions.Session = Session
    mod = types.ModuleType("requests")
    mod.sessions = sessions
    return mod, sessions, Session, sent


class GuardTests(unittest.TestCase):
    def setUp(self):
        mod, sessions, self.Session, self.sent = stub_requests()
        patcher = mock.patch.dict(
            sys.modules, {"requests": mod, "requests.sessions": sessions}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.uninstall = authors_target.install_host_guard(TARGET)
        self.addCleanup(self.uninstall)
        self.session = self.Session()

    def urls(self):
        return [u for _, u, _ in self.sent]

    def test_production_links_go_to_the_target_instead(self):
        self.session.request("POST", PRODUCTION + "/api/records/abc/draft/review")
        self.assertEqual(self.urls(), [TARGET + "api/records/abc/draft/review"])

    def test_the_dev_host_goes_to_the_target_too(self):
        self.session.request("POST", DEV + "//api/records")
        self.assertEqual(self.urls(), [TARGET + "/api/records"])

    def test_path_query_and_arguments_are_kept(self):
        self.session.request(
            "GET", PRODUCTION + "/api/records?q=a%20b&size=1", headers={"A": "b"}
        )
        method, url, kw = self.sent[0]
        self.assertEqual(url, TARGET + "api/records?q=a%20b&size=1")
        self.assertEqual(kw, {"headers": {"A": "b"}})

    def test_no_request_ever_reaches_production_or_dev(self):
        for host in (PRODUCTION, DEV, PRODUCTION.upper(), "https://authors.library.caltech.edu:443"):
            self.session.request("PUT", host + "/api/x")
        for url in self.urls():
            self.assertTrue(url.startswith(TARGET), url)

    def test_the_target_itself_is_unchanged(self):
        self.session.request("GET", TARGET + "api/records")
        self.assertEqual(self.urls(), [TARGET + "api/records"])

    def test_other_hosts_are_left_alone(self):
        for url in (
            "https://api.crossref.org/works/10.1/x",
            "https://api.ror.org/organizations",
            "https://feeds.library.caltech.edu/people/people.csv",
            "https://data.caltech.edu/api/records",
        ):
            self.session.request("GET", url)
        self.assertEqual(
            self.urls(),
            [
                "https://api.crossref.org/works/10.1/x",
                "https://api.ror.org/organizations",
                "https://feeds.library.caltech.edu/people/people.csv",
                "https://data.caltech.edu/api/records",
            ],
        )

    def test_a_host_that_only_contains_the_name_is_left_alone(self):
        url = "https://authors.library.caltech.edu.example.org/x"
        self.session.request("GET", url)
        self.assertEqual(self.urls(), [url])

    def test_uninstall_restores_the_original(self):
        self.uninstall()
        self.session.request("GET", PRODUCTION + "/api/x")
        self.assertEqual(self.urls(), [PRODUCTION + "/api/x"])
        # and the fixture's own cleanup may call uninstall again safely
        self.uninstall()

    def test_installing_twice_does_not_stack(self):
        again = authors_target.install_host_guard(TARGET)
        self.addCleanup(again)
        self.session.request("GET", PRODUCTION + "/api/x")
        self.assertEqual(self.urls(), [TARGET + "api/x"])


class GuardSchemeAndStackingTests(unittest.TestCase):
    def setUp(self):
        mod, sessions, self.Session, self.sent = stub_requests()
        patcher = mock.patch.dict(
            sys.modules, {"requests": mod, "requests.sessions": sessions}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_scheme_comes_from_the_target(self):
        undo = authors_target.install_host_guard("http://localhost:8080/")
        self.addCleanup(undo)
        self.Session().request("GET", PRODUCTION + "/api/x")
        self.assertEqual(self.sent[0][1], "http://localhost:8080/api/x")

    def test_undoing_two_installs_in_either_order_restores_the_original(self):
        original = self.Session.request
        for order in ((0, 1), (1, 0)):
            first = authors_target.install_host_guard(TARGET)
            second = authors_target.install_host_guard(TARGET)
            undos = (first, second)
            for i in order:
                undos[i]()
            self.assertIs(self.Session.request, original, order)


class GuardArgumentTests(unittest.TestCase):
    def test_a_target_that_is_not_https_url_is_a_value_error(self):
        mod, sessions, _, _ = stub_requests()
        with mock.patch.dict(sys.modules, {"requests": mod, "requests.sessions": sessions}):
            for bad in ("", "not a url", "ftp://x/", "https://"):
                with self.assertRaises(ValueError, msg=bad):
                    authors_target.install_host_guard(bad)

    def test_production_is_refused_as_a_target(self):
        # -url is for test instances; production is what no flag means
        mod, sessions, _, _ = stub_requests()
        with mock.patch.dict(sys.modules, {"requests": mod, "requests.sessions": sessions}):
            for bad in (PRODUCTION + "/", PRODUCTION.upper() + "/", PRODUCTION + ":443/"):
                with self.assertRaises(ValueError, msg=bad):
                    authors_target.install_host_guard(bad)

    def test_the_dev_host_is_allowed_as_a_target(self):
        # it may be the AWS test instance; redirecting it to itself is harmless
        mod, sessions, Session, sent = stub_requests()
        with mock.patch.dict(sys.modules, {"requests": mod, "requests.sessions": sessions}):
            undo = authors_target.install_host_guard(DEV + "/")
            self.addCleanup(undo)
            Session().request("GET", DEV + "/api/x")
            Session().request("GET", PRODUCTION + "/api/x")
        self.assertEqual([u for _, u, _ in sent], [DEV + "/api/x", DEV + "/api/x"])


if __name__ == "__main__":
    unittest.main()
