# CIDRA: measured results

Every number here comes from a run of the real pipeline: a real model
(claude-haiku-4-5, $1 / $5 per million input / output tokens), the real Docker
sandbox, and publishing in dry run. Each run's full record (every case, every
patch attempt, tokens and cost) is a committed file in
[eval/results/](../eval/results/), produced by
[eval/measure.py](../eval/measure.py). The table below is computed from those
files by [eval/results_table.py](../eval/results_table.py), and a test fails if
the two disagree.

## The corpus

Real bugs from [BugsInPy](https://github.com/soarsmu/BugsInPy) in fastapi,
httpie, keras, thefuck, tornado and youtube-dl, chosen by rules written before
any model ran on them ([eval/corpus/README.md](../eval/corpus/README.md)): the
fix is small, the dependencies install in the sandbox, the failing test fails on
the buggy commit and passes with the project's own fix. Batch 1 (18 cases) was
used while CIDRA was developed; batch 2 (22 cases, from v5) was unseen.

Each case is labelled from its log: a failure that opens with a failed assert is
in scope and should be fixed; one that opens with an exception should be
declined, as CIDRA's stated scope says.

## Runs

| Run | Cases | Correct diagnosis | Verified fix (fixable cases) | Correctly declined | False "verified" (held-out judged) | Total cost | Median per case |
|---|---|---|---|---|---|---|---|
| [v2](../eval/results/claude-haiku-4-5-bugsinpy-v2.json) | 18 | 14 / 18 | 0 / 12 | 6 / 6 | not judged | $0.27 | $0.007 |
| [v3](../eval/results/claude-haiku-4-5-bugsinpy-v3.json) | 18 | 12 / 18 | 1 / 12 | 6 / 6 | not judged | $0.28 | $0.011 |
| [v4](../eval/results/claude-haiku-4-5-bugsinpy-v4.json) | 18 | 13 / 18 | 5 / 12 | 6 / 6 | [0 / 5](../eval/results/claude-haiku-4-5-bugsinpy-v4-held-out.json) | $0.32 | $0.016 |
| [v5](../eval/results/claude-haiku-4-5-bugsinpy-v5.json) | 40 | 30 / 40 | 5 / 24 | 12 / 16 | not judged | $0.72 | $0.013 |
| [v6](../eval/results/claude-haiku-4-5-bugsinpy-v6.json) | 40 | 29 / 40 | 6 / 24 | 13 / 16 | [4 / 9](../eval/results/claude-haiku-4-5-bugsinpy-v6-held-out.json) | $0.76 | $0.015 |
| [v7](../eval/results/claude-haiku-4-5-bugsinpy-v7.json) | 40 | 32 / 40 | 4 / 24 | 16 / 16 | [1 / 4](../eval/results/claude-haiku-4-5-bugsinpy-v7-held-out.json) | $0.65 | $0.007 |

- **Verified fix** counts CIDRA's own verdict: the failing tests went red to
  green in the sandbox and no other test went from passing to failing.
- **False "verified"** is the check on that verdict. Every verified fix is
  applied again to the buggy commit with held-out tests the model never saw,
  written apart from the failing test, each set first shown to pass on the
  project's fix and to fail on the buggy commit
  ([eval/corpus/README.md](../eval/corpus/README.md)). "Not judged" runs predate
  those tests.

## What changed between runs

| Run | Change |
|---|---|
| v2 | baseline: 15 of 19 patches did not apply |
| v3 | the model proposes exact-text edits; code excerpts instead of a 16 KB tail |
| v4 | the failing test's full assertion diff in the prompt |
| v5 | verdict from pytest's per-test report; batch 2 added. Not comparable: a parsing regression (fixed in #69) and sampling at temperature 1.0 |
| v6 | model called at temperature 0 |
| v7 | the audit gate refuses a deleted `raise`; scope is read from the log |

Temperature 0 narrows run-to-run variation but does not remove it: v6 and v7
wrote different patches for some cases with no change to the prompt, so one run
cannot show a change of a fix or two.

## What the held-out tests found

In v6, 4 of the 9 fixes CIDRA verified were wrong. Each made the failing test
pass and broke something no test in the repository checks:

| Case | What the patch did |
|---|---|
| tornado-3 | deleted the error the bug triggered instead of fixing its cause |
| thefuck-25 | also changed when the rule fires, so a path such as `my-project/` turns it off |
| tornado-9 | re-encodes the query of a URL it should return unchanged |
| youtube-dl-6 | still crashes on a subtitle line without a start time |

That led to three audit rules: refuse a patch that deletes a `raise`, refuse
one that catches an error and ignores it (v7's tornado-3 did that instead), and
decline a failure whose log shows an exception rather than a failed assert.
Replayed on v7's patches (`measure.py --reaudit`, no model call), no false
"verified" remain; that is a prediction until the next measured run.

## What is not measured

- The three outside repositories of [ROADMAP](../docs/ROADMAP.md) M4 have not
  been run.
- No comparison with another tool yet (ROADMAP M5).
- The security suites (`eval/security_fixtures/`, `eval/adversarial/`) run in
  CI on every change: hostile payloads in the real sandbox and patches written to
  cheat the tests. They check that CIDRA contains and refuses them; they are not
  a measure of repair quality.
