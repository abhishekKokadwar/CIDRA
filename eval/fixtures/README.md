# Fixture corpus

Seven fixtures. See [../../docs/5_fixtures.md](../../docs/5_fixtures.md) for the spec.

| ID | Class | Branch in `cidra-practice` |
|---|---|---|
| F-01 | missing_dependency | `fix-01-missing-dep` |
| F-01b | missing_dependency (import name != PyPI name) | `fix-01b-transitive-dep` |
| F-02 | assertion_error | `fix-02-assertion` |
| F-02b | assertion_error (off-by-one, not a literal) | `fix-02b-loop-boundary` |
| F-03 | env_config_error | `fix-03-env-config` |
| F-04 | flaky_test | `fix-04-flaky` |
| N-01 | unknown — must NOT be "fixed" | `neg-01-logic-bug` |

## local.log vs raw.log

`local.log` is pytest output captured on this machine — the offline stand-in so Tier 1
and Tier 2 run before the practice repo is pushed. `raw.log` is real GitHub Actions
output and takes precedence once captured (`gh run view <id> --log`).

Real CI logs carry ISO timestamps, ANSI colour and `##[group]` markers that `local.log`
lacks. Isolation handles both, but **re-run the eval after capturing `raw.log`** — that
is the honest number.

## Running

```bash
python eval/run_eval.py            # tier 1: isolation only, free, instant
python eval/run_eval.py --tier 2   # tier 2: + LLM classification, costs cents
```

## Measured results: `eval/measure.py`

```bash
python eval/measure.py --stub                      # this corpus, scripted model, no cost
python eval/measure.py --validate                  # check the held-out sets, no model call
python eval/measure.py --stub --corpus eval/corpus # another corpus folder
```

A corpus is a folder with one sub-folder per fixture. Each fixture holds:

| File | Purpose |
|---|---|
| `meta.json` | Where the failure lives (fields below) |
| `expected.json` | `expected_outcome` and `expected_analysis.category` |
| `raw.log` | The CI log of the failing run. Stored, so no fetch and no token |
| `fake_llm.json` | Scripted answers for `--stub` |
| `held_out/test_*.py` | Optional extra tests the model never sees |
| `cheat_llm.json` | Optional deliberately wrong patch the held-out tests must catch |

`meta.json` fields. Only `class` is needed for a fixture in the practice repo; the
rest have defaults that match it.

| Field | Default | Meaning |
|---|---|---|
| `class` | | Failure class, for reporting |
| `repo_url` | the practice repo clone | Git URL or path. Cloned once into `worktrees/corpus/` |
| `failing_ref` | `origin/<gh_branch>` | Commit (or ref) whose CI failed |
| `fix_ref` | `origin/main` | Commit (or ref) with the known-good fix |
| `log` | `raw.log` | Log file name in the fixture folder |
| `held_out_paths` | `["tests"]` | Paths taken from `fix_ref` as the held-out tests |
| `install_command` | `pip install --quiet -r requirements.txt` | Must be a `pip install`; the sandbox appends `--target` |
| `test_command` | `pytest -q 2>&1` | Run in the sandbox with no network |
| `python_version` | read from the repo's workflow | 3.7 to 3.13 |
| `gh_repo`, `gh_run_id` | | Only used to fetch the log when none is stored |

### When a verified fix is judged

A verified fix is re-applied to the failing commit and run against the held-out
tests. That result only counts toward the false-verified rate when the held-out
set is itself validated, on every run:

1. it passes on `fix_ref`;
2. it catches `cheat_llm.json`, if the fixture has one;
3. it shows something the failing run did not: a test that fails on the failing
   commit only once the held-out tests are added, or the cheat patch being caught.

Rule 3 is why the fix commit's tests are often not enough. If the only test they
add is the one already failing in the CI log, a patch can be written to satisfy
exactly that test and nothing here would notice. Such a fixture is still measured
for diagnosis and fix rate, but it is listed as "not judged" and left out of the
false-verified rate until it gets tests of its own in `held_out/`.
