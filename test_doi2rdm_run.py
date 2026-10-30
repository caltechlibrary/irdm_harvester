"""Tests for doi2rdm_run, using a fake doi2rdm so no network is needed.

Run with: python3 -m unittest test_doi2rdm_run
"""

import json
import os
import stat
import tempfile
import unittest

from doi2rdm_run import Doi2rdmError, doi2rdm

DOI = "10.1000/example"


class FakeDoi2rdm:
    """A throwaway executable that prints, writes to stderr and exits."""

    def __init__(self, stdout="", stderr="", code=0):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "doi2rdm")
        with open(self.path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write(f"printf '%s' {stdout!r}\n")
            f.write(f"printf '%s' {stderr!r} >&2\n")
            f.write(f"exit {code}\n")
        os.chmod(self.path, os.stat(self.path).st_mode | stat.S_IXUSR)

    def close(self):
        self.dir.cleanup()


def run_fake(testcase, **kw):
    fake = FakeDoi2rdm(**kw)
    testcase.addCleanup(fake.close)
    return fake.path


class ConvertTests(unittest.TestCase):
    def test_success_returns_the_record(self):
        cmd = run_fake(self, stdout=json.dumps({"id": 1}))
        self.assertEqual(doi2rdm(DOI, command=cmd), {"id": 1})

    def test_success_passes_warnings_to_stderr_not_stdout(self):
        cmd = run_fake(self, stdout="{}", stderr="doi2rdm: w\n")
        import contextlib, io

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            doi2rdm(DOI, command=cmd)
        self.assertIn("doi2rdm: w", err.getvalue())

    def raises(self, code, stderr="", stdout=""):
        cmd = run_fake(self, stdout=stdout, stderr=stderr, code=code)
        with self.assertRaises(Doi2rdmError) as cm:
            doi2rdm(DOI, command=cmd)
        return cm.exception

    def test_exit_1_is_not_found(self):
        e = self.raises(1, "no record")
        self.assertEqual(e.kind, "not_found")
        self.assertIn("not found in Crossref or DataCite", e.message())
        self.assertIn(DOI, e.message())

    def test_exit_2_is_a_harvester_bug_not_not_found(self):
        e = self.raises(2, "bad command line")
        self.assertEqual(e.kind, "usage")
        self.assertNotIn("not found", e.message().lower())
        self.assertIn("system", e.message().lower())

    def test_exit_65_names_the_doi_and_the_reason(self):
        e = self.raises(65, "resource type 'x' not mapped")
        self.assertEqual(e.kind, "data")
        self.assertIn(DOI, e.message())
        self.assertIn("resource type", e.message())
        self.assertIn("system", e.message().lower())

    def test_exit_66_and_78_are_configuration_problems(self):
        for code in (66, 78):
            e = self.raises(code, "options.yaml: bad")
            self.assertEqual(e.kind, "config", code)
            self.assertIn("options.yaml", e.message())
            self.assertIn("system", e.message().lower())

    def test_exit_69_and_75_are_retry_later_not_unknown_doi(self):
        for code in (69, 75):
            e = self.raises(code, "503")
            self.assertEqual(e.kind, "retry", code)
            self.assertIn("later", e.message().lower())
            self.assertNotIn("not found", e.message().lower())
            self.assertIn("system", e.message().lower())

    def test_exit_70_74_and_unknown_codes_are_system_errors(self):
        for code in (70, 74, 99):
            e = self.raises(code, "boom")
            self.assertEqual(e.kind, "system", code)
            self.assertIn(str(code), e.message())
            self.assertIn("system", e.message().lower())

    def test_not_found_wording_only_for_exit_1(self):
        # dimensions.yaml reacts to "not found" in the error output, so
        # stderr text must not trigger it for any other code.
        for code in (2, 65, 66, 69, 70, 74, 75, 78):
            e = self.raises(code, "record NOT FOUND in table")
            self.assertNotIn("not found", e.message().lower(), code)

    def test_message_is_one_line_and_safe_for_github_output(self):
        e = self.raises(65, "line one\nline=two\n\"quoted\" (paren): colon")
        msg = e.message()
        self.assertNotIn("\n", msg)
        for ch in "=:()\"'":
            self.assertNotIn(ch, msg)

    def test_long_stderr_is_truncated(self):
        e = self.raises(70, "x" * 5000)
        self.assertLess(len(e.message()), 600)

    def test_bad_json_on_stdout_is_a_system_error(self):
        e = self.raises(0, stdout="not json")
        self.assertEqual(e.kind, "system")
        self.assertIn("system", e.message().lower())

    def test_missing_executable_is_a_system_error(self):
        with self.assertRaises(Doi2rdmError) as cm:
            doi2rdm(DOI, command="/nonexistent/doi2rdm")
        self.assertEqual(cm.exception.kind, "system")
        self.assertIn("system", cm.exception.message().lower())


REAL = os.environ.get("DOI2RDM_BIN")


@unittest.skipUnless(REAL, "set DOI2RDM_BIN to a doi2rdm 0.1.0 or later")
class RealBinaryTests(unittest.TestCase):
    """Cases a real doi2rdm answers without the network."""

    def test_missing_options_file_is_config_66(self):
        with self.assertRaises(Doi2rdmError) as cm:
            doi2rdm(DOI, options="/nonexistent/options.yaml", command=REAL)
        self.assertEqual(cm.exception.returncode, 66)
        self.assertEqual(cm.exception.kind, "config")
        self.assertIn("options.yaml", cm.exception.message())

    def test_invalid_options_file_is_config_78(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.yaml")
            with open(bad, "w") as f:
                f.write("a: [unclosed\n")
            with self.assertRaises(Doi2rdmError) as cm:
                doi2rdm(DOI, options=bad, command=REAL)
        self.assertEqual(cm.exception.returncode, 78)
        self.assertEqual(cm.exception.kind, "config")
        self.assertIn("bad.yaml", cm.exception.message())


if __name__ == "__main__":
    unittest.main()
