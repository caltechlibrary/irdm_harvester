# TODO

## Tell a bad doi2rdm configuration apart from an unknown DOI

`harvest.py` calls `doi2rdm options.yaml DOI` and reads its exit code
(around line 689-698):

```python
except subprocess.CalledProcessError as e:
    if e.returncode == 2:
        print(f"error=DOI {doi} not found in Crossref or DataCite")
    else:
        cleaned = format_error(format_exc())
        print(f"error= system error with doi2rdm {cleaned}")
    break
```

`doi2rdm` (irdmtools) exits with 2 when it cannot read a file it is given, so
today a missing `options.yaml` is reported as "DOI not found". irdmtools is
adding an optional `symbols:` key to the options YAML (a path to an override
table for converting CrossRef markup and MathML, resolved relative to the
options file). A bad path there must not look like an unknown DOI either, so
the new failures use the workspace exit codes (workspace DR-0014), which do
not collide with 2:

| Code | Class | doi2rdm meaning |
|------|-------|-----------------|
| 66 | `no_input` | the symbols file named in the options is missing |
| 78 | `config` | the symbols file is present but invalid |

- [ ] `harvest.py`, the `CalledProcessError` handler near line 694: add a branch
      for 66 and 78 (and later 65 and 70 when `doi2rdm` adopts the rest of
      DR-0014) that prints a configuration message naming `options.yaml`, not a
      DOI message. A configuration error will fail every DOI, so it should stop
      the run (the existing `break` does) rather than skip one record.
- [ ] Decide whether a missing `options.yaml` (exit 2 today) should keep being
      read as "DOI not found". It will, until `doi2rdm` adopts the DR-0014
      codes; check that `options.yaml` exists before the loop instead.
- [ ] If `options.yaml` ever names `symbols:`, keep the file beside it: the path
      is read relative to `options.yaml`, not to the current directory.

`doi2rdm`'s stdout stays JSON and its exit code 2 stays "not found"; this
harvester depends on both.
