"""Run doi2rdm and turn its exit status into a message the workflows read.

doi2rdm 0.1.0 and later use the workspace exit codes (DR-0014):

  0 ok, 1 DOI not found, 2 bad command line, 65 record not convertible,
  66 missing file, 69 service unreachable, 70 bug, 74 write failed,
  75 rate limited, 78 bad configuration.

The workflows copy harvest.py's standard output into $GITHUB_OUTPUT and react
to words in the "error" value: "system" and "skipping" fail the job and
dimensions.yaml also reacts to "not found". So "not found" is said only for
exit 1, every other failure says "system", and a message is one line with
none of the characters format_error removes.
"""

import json
import re
import subprocess
import sys

from utils import format_error

MAX_DETAIL = 300

# exit code -> kind
KINDS = {
    1: "not_found",
    2: "usage",
    65: "data",
    66: "config",
    78: "config",
    69: "retry",
    75: "retry",
}


class Doi2rdmError(Exception):
    """doi2rdm failed. kind is not_found, usage, data, config, retry or system."""

    def __init__(self, doi, returncode, stderr="", cause=""):
        self.doi = doi
        self.returncode = returncode
        self.stderr = stderr or ""
        self.cause = cause
        self.kind = KINDS.get(returncode, "system")
        super().__init__(self.message())

    def detail(self):
        """The reason doi2rdm gave, safe for the error line, kept short."""
        text = self.cause or self.stderr.strip()
        # "not found" belongs to exit 1 alone (dimensions.yaml matches it)
        text = re.sub(r"not found", "missing", text, flags=re.IGNORECASE)
        return format_error(text)[:MAX_DETAIL]

    def message(self):
        """One line for the workflows: the value of "error=" ."""
        doi, detail = self.doi, self.detail()
        if self.kind == "not_found":
            return f"DOI {doi} not found in Crossref or DataCite"
        if self.kind == "usage":
            return f"system error doi2rdm was called wrongly, a bug in harvest.py {detail}"
        if self.kind == "data":
            return f"system error doi2rdm could not convert DOI {doi}, a person needs to look at it {detail}"
        if self.kind == "config":
            return f"system error doi2rdm configuration problem, every DOI will fail {detail}"
        if self.kind == "retry":
            return f"system error Crossref or DataCite unavailable for DOI {doi}, try again later {detail}"
        return f"system error with doi2rdm exit {self.returncode} {detail}"


def convert(doi, options="options.yaml", command="doi2rdm", run=subprocess.run):
    """Return the RDM record doi2rdm makes for doi, or raise Doi2rdmError.

    Standard output is the JSON and nothing else. Standard error is captured;
    on success it holds conversion warnings and is passed to our standard
    error, on failure it is the reason.
    """
    try:
        done = run(
            [command, options, doi],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError as e:
        raise Doi2rdmError(doi, None, cause=f"cannot run {command} {e}")
    if done.returncode != 0:
        raise Doi2rdmError(doi, done.returncode, done.stderr)
    if done.stderr:
        sys.stderr.write(done.stderr)
    try:
        return json.loads(done.stdout)
    except ValueError as e:
        raise Doi2rdmError(doi, None, cause=f"output is not JSON {e}")
