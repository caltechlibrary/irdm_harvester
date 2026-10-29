"""Tests for the `authors` harvest type of harvest.py (a new version of an
existing record, from a source record).

harvest.py is a script and cannot be imported here (it needs dimcli and
idutils), so it is run with runpy against stubbed modules: no network and no
third-party packages are used. What is checked is how the run reaches the
instance: every request to it, and every caltechdata_api call, must carry the
target's `verify` and `local`, and nothing may rewrite hosts behind the
library's back.

Run with: python3 -m unittest test_authors_path
"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import authors_target

HERE = Path(__file__).resolve().parent
LOCAL = "https://127.0.0.1:5000/"
DEV = "https://authors.caltechlibrary.dev/"
PRODUCTION = "https://authors.library.caltech.edu/"
SOURCE = "src11-11111"
DESTINATION = "dst22-22222"


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def run_harvest(*args, source_status=200, draft_status=200, advertised=LOCAL):
    """Run harvest.py with ARGS; return (requests, library calls, output)."""
    gets, calls = [], []

    def get(url, *a, **kw):
        gets.append((url, kw))
        if url.endswith(f"api/records/{SOURCE}"):
            return Response(source_status, {"files": {"default_preview": "a.txt"}})
        if url.endswith(f"api/records/{SOURCE}/draft"):
            return Response(draft_status, {"files": {"default_preview": "a.txt"}})
        if "size=1" in url:
            return Response(200, {"links": {"self": advertised + "api/records"}})
        return Response(200, {})

    def library(name, result=None):
        def fn(*a, **kw):
            calls.append((name, a, kw))
            return result

        return fn

    requests = types.ModuleType("requests")
    requests.get = get
    requests.sessions = types.ModuleType("requests.sessions")
    session = type("Session", (), {"request": lambda *a, **k: None})
    requests.sessions.Session = session
    run_harvest.session, run_harvest.original = session, session.request
    idutils = types.ModuleType("idutils")
    idutils.normalize_doi = idutils.normalize_orcid = lambda x: x
    api = types.ModuleType("caltechdata_api")
    api.caltechdata_write = library("caltechdata_write")
    api.caltechdata_edit = library("caltechdata_edit", "id")
    api.get_files_from_record = library("get_files_from_record", {"a.txt": {}})
    api.download_files_from_record = library("download_files_from_record")
    stubs = {
        "requests": requests,
        "requests.sessions": requests.sessions,
        "dimcli": mock.MagicMock(),
        "idutils": idutils,
        "caltechdata_api": api,
    }
    out = io.StringIO()
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
        sys.modules, stubs
    ), mock.patch.dict(
        os.environ, {"RDMTOK": "t", "AUTHORS_COMMUNITY": "community-1"}
    ), mock.patch.object(
        sys, "path", [str(HERE)] + sys.path
    ), mock.patch.object(
        sys,
        "argv",
        ["harvest.py", "authors", "-authors-source", SOURCE]
        + ["-authors-destination", DESTINATION, "-actor", "a", "-message", "m"]
        + list(args),
    ):
        # modules that bound the real requests when first imported
        for name in ("check_doi", "wos"):
            sys.modules.pop(name, None)
        Path(tmp, "harvested_dois.txt").write_text("")
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out):
                try:
                    runpy.run_path(str(HERE / "harvest.py"), run_name="__main__")
                except SystemExit:
                    pass
        finally:
            os.chdir(cwd)
            for name in ("check_doi", "wos"):
                sys.modules.pop(name, None)
    return gets, calls, out.getvalue()


def named(calls, name):
    found = [(a, kw) for n, a, kw in calls if n == name]
    assert len(found) == 1, f"{name} was called {len(found)} times"
    return found[0]


class LocalTests(unittest.TestCase):
    """-local: a self-signed instance at 127.0.0.1:5000."""

    def setUp(self):
        self.gets, self.calls, self.out = run_harvest("-local")

    def test_the_run_finished(self):
        self.assertNotIn("error", self.out)
        named(self.calls, "caltechdata_edit")

    def test_every_request_to_the_instance_skips_tls_verification(self):
        self.assertTrue(self.gets)
        for url, kw in self.gets:
            self.assertTrue(url.startswith(LOCAL), url)
            self.assertIs(kw.get("verify", True), False, url)

    def test_the_downloads_target_the_instance(self):
        for name in ("get_files_from_record", "download_files_from_record"):
            _, kw = named(self.calls, name)
            self.assertIs(kw.get("local"), True, name)
            self.assertIs(kw.get("verify", True), False, name)

    def test_the_new_version_targets_the_instance(self):
        _, kw = named(self.calls, "caltechdata_edit")
        self.assertIs(kw.get("local"), True)
        self.assertIs(kw.get("verify", True), False)

    def test_the_draft_source_is_reached_with_the_same_settings(self):
        gets, calls, out = run_harvest("-local", source_status=404)
        drafts = [kw for url, kw in gets if url.endswith(f"{SOURCE}/draft")]
        self.assertEqual(len(drafts), 1)
        self.assertIs(drafts[0].get("verify", True), False)
        self.assertEqual(drafts[0]["headers"]["Authorization"], "Bearer t")


class LocalLinksCheckTests(unittest.TestCase):
    """-local stops before any write when the instance advertises another host."""

    def test_a_local_run_checks_the_instance_first(self):
        gets, calls, out = run_harvest("-local")
        self.assertTrue(gets[0][0].startswith(LOCAL + "api/records?"), gets[0][0])
        self.assertIn("size=1", gets[0][0])

    def test_an_instance_advertising_production_is_never_written_to(self):
        gets, calls, out = run_harvest("-local", advertised=PRODUCTION)
        self.assertIn("error=", out)
        self.assertIn("SITE_UI_URL", out)
        self.assertEqual(calls, [])
        for url, kw in gets:
            self.assertNotIn("api/records/" + SOURCE, url)

    def test_the_dev_host_is_not_checked(self):
        gets, calls, out = run_harvest("-test")
        self.assertFalse([u for u, kw in gets if "size=1" in u])


class DevTests(unittest.TestCase):
    """-test: the dev host, a real certificate, never verify=False."""

    def setUp(self):
        self.gets, self.calls, self.out = run_harvest("-test")

    def test_requests_are_verified_and_go_to_the_dev_host(self):
        self.assertTrue(self.gets)
        for url, kw in self.gets:
            self.assertTrue(url.startswith(DEV), url)
            self.assertIs(kw.get("verify", True), True, url)

    def test_library_calls_are_not_local_and_verify(self):
        for name in (
            "get_files_from_record",
            "download_files_from_record",
            "caltechdata_edit",
        ):
            _, kw = named(self.calls, name)
            self.assertIsNot(kw.get("local"), True, name)
            self.assertIs(kw.get("verify", True), True, name)


class NoHostRewriteTests(unittest.TestCase):
    """Test instances are configured to advertise themselves, so nothing
    rewrites hosts inside the library's requests."""

    def test_authors_target_has_no_host_guard(self):
        self.assertFalse(hasattr(authors_target, "install_host_guard"))

    def test_a_local_run_leaves_session_request_alone(self):
        run_harvest("-local")
        self.assertIs(run_harvest.session.request, run_harvest.original)


if __name__ == "__main__":
    unittest.main()
