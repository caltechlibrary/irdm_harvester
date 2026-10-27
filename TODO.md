# TODO

## Read the new `doi2rdm` exit codes and give better feedback

`harvest.py` calls `doi2rdm options.yaml DOI` and reads its exit code (around
line 689-698):

```python
except subprocess.CalledProcessError as e:
    if e.returncode == 2:
        print(f"error=DOI {doi} not found in Crossref or DataCite")
    else:
        cleaned = format_error(format_exc())
        print(f"error= system error with doi2rdm {cleaned}")
    break
```

The `irdmtools` release that carries the `doi2rdm` text normalization changes
**every** `doi2rdm` exit code to the workspace convention (workspace DR-0014;
`irdmtools/DR-0003`). It is a breaking change for this reader: "not found" was 2
and is now **1**, and 2 now means a bad command line. Until `harvest.py` is
updated, a not-found DOI is reported as a "system error with doi2rdm" and a
command line error as "DOI not found". Both still stop the run, as the `break`
above does.

| Code | Class | `doi2rdm` meaning | What the harvester could say or do |
|------|-------|-------------------|-------------------------------------|
| 0 | ok | the record was written | continue |
| 1 | negative | CrossRef and DataCite both have no record for the DOI | "DOI not found in Crossref or DataCite"; skip this DOI |
| 2 | usage | a bad command line | a bug in `harvest.py`; stop |
| 65 | data | the record could not be converted (for example a resource type `options.yaml` does not map), or a `-diff` file is not JSON | name the DOI and the message; skip this DOI and report it for a person to look at |
| 66 | no_input | `options.yaml`, a `-diff` file or the symbols file is missing | a configuration problem that will fail every DOI; stop and name the file |
| 69 | unavailable | CrossRef or DataCite cannot be reached or failed (network, timeout, HTTP 5xx) | the DOI may exist; retry later, and do not record it as unknown |
| 70 | internal | a bug in `doi2rdm` | stop; report the stderr text |
| 74 | io | writing the record failed | stop; report |
| 75 | temp_fail | rate limited (HTTP 429) | wait and retry |
| 78 | config | `options.yaml` or the symbols file is present but invalid | a configuration problem for every DOI; stop and name the file |

- [ ] `harvest.py`, the `CalledProcessError` handler near line 694: branch on the
      codes above instead of treating 2 as "not found". A 66 or 78 will fail
      every DOI, so it should stop the run (the existing `break` does); 1 and 65
      concern one DOI; 69 and 75 are worth a retry later. Print `e.stderr` text
      too: `doi2rdm` writes the reason there, and since this release also writes
      one line per conversion warning (`doi2rdm: DOI: field: code: fragment`).
      Capture it with `stderr=subprocess.PIPE` (today it goes to the terminal).
- [ ] Do not read stdout for anything but the record: it is the JSON and nothing
      else, as before.
- [ ] If `options.yaml` ever names `symbols:` (an optional crossrefapi override
      for the title and abstract conversion), keep that file beside it: the path
      is read relative to `options.yaml`, not to the current directory.
- [ ] Deploy `harvest.py` and the new `doi2rdm` together: either one alone
      misreads the other's exit codes.
