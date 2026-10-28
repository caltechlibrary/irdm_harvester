#!/bin/bash
#
# run_local.bash runs the steps of .github/workflows/crossref_ror.yaml on this
# machine, so the pipeline can be debugged without GitHub. It is a convenience
# for debugging, not a replacement for the workflow: it does not run the
# GitHub runner, the matrix-output actions, secrets, or git-auto-commit.
#
# It works in a scratch copy of this directory, so last_run.txt and
# harvested_dois.txt here are never touched. It reads what each step prints
# the way GitHub reads $GITHUB_OUTPUT, and applies the same checks the
# workflow steps make on the "error" value.
#
# USAGE
#
#   ./run_local.bash [-h] [-c] DOI [DOI ...]
#
#   -c    take the DOI list from CrossRef (harvest.py crossref -print) the way
#         the workflow does, instead of from the command line
#   -h    show this help
#
# ENVIRONMENT
#
#   HARVEST_CMD               default "uv run harvest.py"; the harvest.py
#                             command, in the scratch copy
#   HARVEST_ARGS              default "-local"; extra harvest.py options for
#                             each DOI. -local needs RDMTOK and
#                             AUTHORS_COMMUNITY and a CaltechAUTHORS at
#                             https://127.0.0.1:5000 (see authors_target.py)
#   doi2rdm and options.yaml  doi2rdm on PATH should be the version the
#                             workflow would install (installer.sh)
#
# EXIT STATUS
#
#   0 every DOI was harvested or skipped as the workflow would treat as ok
#   1 a step the workflow would fail: a "system" or "skipping" error, a stdout
#     line GitHub would reject, or check_status.py failing
#   2 usage

set -u

HARVEST_CMD=${HARVEST_CMD:-uv run harvest.py}
HARVEST_ARGS=${HARVEST_ARGS:--local}
HERE=$(cd "$(dirname "$0")" && pwd)

use_crossref=0
while getopts "ch" opt; do
    case $opt in
    c) use_crossref=1 ;;
    h)
        sed -n '3,/^set -u/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    *) exit 2 ;;
    esac
done
shift $((OPTIND - 1))
if [ "$use_crossref" = 0 ] && [ $# -eq 0 ]; then
    echo "usage: $0 [-h] [-c] DOI [DOI ...]" >&2
    exit 2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/irdm_harvester_local.XXXXXX") || exit 2
for f in "$HERE"/*.py "$HERE"/options.yaml "$HERE"/pyproject.toml \
    "$HERE"/uv.lock "$HERE"/harvested_dois.txt "$HERE"/last_run.txt; do
    [ -f "$f" ] && cp "$f" "$WORK"/
done
cd "$WORK" || exit 2
cp harvested_dois.txt harvested_dois.before
echo "work directory: $WORK"

# A line GitHub accepts in $GITHUB_OUTPUT is NAME=value (or NAME<<DELIMITER).
valid_output_line() {
    [ -z "$1" ] && return 0
    [[ "$1" =~ ^[^=[:space:]][^=]*= ]] || [[ "$1" =~ ^[^=[:space:]][^\<]*\<\< ]]
}

fail=0

echo "== get-crossref"
if [ "$use_crossref" = 1 ]; then
    # shellcheck disable=SC2086
    $HARVEST_CMD crossref -print >step1.out 2>step1.err
    echo "exit $?"
    dois=$(sed -n 's/^dois= *//p' step1.out | tail -1)
    message=$(sed -n 's/^message= *//p' step1.out | tail -1)
else
    dois="$*"
    message="Local test run by ${USER:-someone}"
fi
echo "dois: $dois"
[ -z "$dois" ] && echo "no DOIs, nothing to do" && exit 0

echo "== prepare-dois"
DOI="$dois" python3 split_doi.py >step2.out
cat step2.out
matrix=$(sed -n 's/^matrix= *//p' step2.out)

echo "== harvest (one job per DOI)"
n=0
index=""
while IFS= read -r doi; do
    n=$((n + 1))
    out="job.$n.out"
    # shellcheck disable=SC2086
    $HARVEST_CMD doi -doi "$doi" -actor "${USER:-someone}" \
        -message "$message" $HARVEST_ARGS >"$out" 2>"job.$n.err"
    status=$?
    printf '%s\t%s\n' "$n" "$doi" >>jobs.tsv
    echo "-- $doi (exit $status)"
    while IFS= read -r line; do
        valid_output_line "$line" ||
            { echo "   GITHUB WOULD REJECT this stdout line: $line"; fail=1; }
    done <"$out"
    sed 's/^/   | /' "$out"
    if [ -s "job.$n.err" ]; then
        echo "   stderr:"
        sed 's/^/   ! /' "job.$n.err" | head -8
    fi
    err=$(sed -n 's/^error=//p' "$out" | tail -1)
    case "$err" in
    *[Ss]ystem*) echo "   workflow: 'System error on DOI' step FAILS (crossref_ror, dimensions)"; fail=1 ;;
    esac
    case "$err" in
    *skipping*) echo "   workflow: 'System intentionally skipped DOI' step FAILS (crossref_ror, dimensions)"; fail=1 ;;
    esac
    case "$err" in
    *"not found"*) echo "   workflow: 'DOI not yet in Crossref or DataCite' step FAILS (dimensions only)" ;;
    esac
done < <(python3 -c 'import json,sys; print("\n".join(json.loads(sys.argv[1])))' "$matrix")

echo "== write-output (matrix outputs, then save_dois.py)"
# The shape cloudposse/github-action-matrix-outputs-read gives: one object per
# output name, keyed by matrix value; a name a job did not set is null and a
# value has no leading space (read from the Report Status log of a real run,
# crossref_ror 2026-10-28).
result=$(python3 - <<'PY'
import json
res = {"doi": {}, "error": {}}
for row in open("jobs.tsv"):
    n, doi = row.rstrip("\n").split("\t", 1)
    got = {}
    for line in open(f"job.{n}.out"):
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1)
            got[k] = v.lstrip()
    for k in res:
        res[k][doi] = got.get(k)
print(json.dumps(res))
PY
)
echo "$result"
python3 save_dois.py "$result"
echo "harvested_dois.txt changes (this scratch copy only):"
diff harvested_dois.before harvested_dois.txt | sed 's/^/   /' || true

echo "== report-status (check_status.py)"
python3 check_status.py "$result" >/dev/null
status=$?
echo "exit $status"
[ "$status" != 0 ] && fail=1

echo
if [ "$fail" = 0 ]; then echo "result: ok"; else echo "result: the workflow would report a failure"; fi
echo "scratch copy kept: $WORK"
exit "$fail"
