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
