# CIDRA Roadmap

**Written:** 2026-10-15 · **Horizon:** about 12 weeks · **Owner:** Abhishek Kokadwar

This is the working plan. It replaces `PRODUCT_PLAN.md` for deciding what to build next; that
file stays as background. Progress is tracked in pull requests and in
[KNOWN_GAPS.md](KNOWN_GAPS.md).

## 1. Direction

CIDRA is a **security-focused CI repair agent**. Its claim:

> When a CI run fails, CIDRA produces a repair a developer can trust without re-checking it:
> the original failure reproduced, a patch that passed a security and test-integrity gate,
> verified on a clean copy with no regressions, and published as a draft pull request with
> the evidence of what was run.

Two rules keep the claim honest:

- **Safety and usefulness are measured together.** A tool that never patches is trivially
  safe. Every safety number is reported next to the fix rate.
- **Security features are not a differentiator until measured against another tool.** The
  comparison in milestone M5 decides what CIDRA can claim.

**Audiences, in order:** real users (developers adding it to a Python repository),
interviewers, research (optional).

**Out of scope for this plan:** languages other than Python, the dashboard, webhook mode
beyond what exists, SBFL, the semantic fix cache, and merging without a human.

## 2. Where it stands (2026-10-17)

| Requirement | Status |
|---|---|
| 1. Authenticate the incoming event | Done: GitHub triggers the Action; webhook mode checks the HMAC |
| 2. Get the failing commit without exposing secrets to its code | Done: Action mode, `cidra fix` (sandboxed first run) and webhook mode (fetches the commit itself) |
| 3. Reproduce the original failure | Done: the CI log's failing tests must fail in the sandbox, twice for a failure CIDRA would patch (G-16, G-17 closed) |
| 4. Generate a patch | Works on 5 of 12 fixable BugsInPy bugs (one doubtful on review); the other 7 need code the model is not shown, or a correct diagnosis |
| 5. Reject test-weakening or unsafe patches | Done: a test file may change only in its asserts' expected values (G-22 closed) |
| 6. Apply to a clean copy and rerun | Done (G-15 fixed) |
| 7. Original failure fixed, no unrelated regressions | Done: the CI's failing tests must pass and no test may go from passing to failing; tests already failing are listed, not blocking |
| 8. Draft PR with evidence of what was tested | Weak: diff and "suite passed" only |

## 3. Milestones

Each milestone ends when its exit criteria hold **and are checked by tests in CI**: its items are in
[requirements.yml](requirements.yml), so the requirements check fails if one loses its passing test.

**Order, as it actually went:** M1 was mostly done when the first real-bug run showed 0 of 12
fixed, so M3's fix-rate work was pulled forward and its target met (5 of 12, 4 genuine on
review). M1 is complete; M2 is done except the cost of a run.

### M1 · Trustworthy "verified" (weeks 1 to 3)

- [x] Run the 15 sandbox safety tests in CI (they skip on a practice-repo check they do not need).
- [x] Record per-test results (pytest JUnit XML) before and after the patch: every sandbox test run asks pytest for a report, read whole from the container; kept as `repro_junit` / `verify_junit` and in `measure.py` results (`tests_before` / `tests_after`). The pass/fail judgement still reads the log; switching it to the report is M2 work.
- [x] G-17: the test the CI log names must be among the sandbox's failures, or the run is "not reproduced".
- [x] No regressions: verified means the target test went red to green **and** no test went green to red. Tests already failing before the patch do not block a verification but are listed.
- [x] G-22: on an `assertion_error` fix, the failing test file may change only in assert expected values.
- [x] G-16: reproduce at least twice for every fixable category; a disagreement means flaky.
- [x] G-18: an install failure or a non-reproduction says why, and points to `install_command` / `test_command`.
- [x] An end-to-end test in CI (done with the 7 practice fixtures and the stub model, `measure.py --check`, instead of a repository built in the test): a small repository created in the test, the stub model, and the full graph to `verified_fix`, `diagnosis_only` and `flaky_detected`.
- [x] The adversarial and security suites run in CI (G-05).

**Exit:** each item above has a CI test that fails on the old behaviour.

### M2 · Evidence in every pull request (weeks 4 to 5)

Each draft PR and job summary carries a short, fixed-format evidence block:

- [x] Failing commit (the patch is made against it), sandbox image and digest, Python version.
- [x] The install and test commands, exactly as run.
- [x] Per-test before/after table: target test(s) red to green, counts for the rest, any test that was already failing.
- [x] Audit gate verdict and any surfaced dependency change.
- [ ] Model, requests, tokens and cost of the run. (Model, requests and tokens done; cost needs a price setting.)
- [x] One command that reruns the verification locally: `cidra verify --sha <commit> --patch <diff>`, printed shell-quoted in every report with a patch.

**Exit:** a reviewer can confirm a fix from the PR alone, and the rerun command reproduces it.

### M3 · Fix real bugs (weeks 6 to 8)

- [x] Study the BugsInPy misses ([v2 result](../eval/results/claude-haiku-4-5-bugsinpy-v2.json)): of 19 patches tried on the 12 fixable bugs, 15 did not apply and 4 were refused for editing test setup. None reached the test run.
- [x] Make patches apply: the model now proposes "replace this exact text" edits and CIDRA builds the diff; an edit whose text is not in the file is reported back to the model.
- [x] Show the model the right part of large files: files are read from the checkout, small ones whole, large ones as excerpts around what the failing test calls (one call deep) and the lines the log names. The changed lines of the reference fix are in view for 6 of 12 fixable BugsInPy bugs, up from 1 (`eval/context_visibility.py`, no model needed).
- The other 6 (fastapi, tornado-1, youtube-dl-2) are reached through framework code the test does not call directly. Coverage-based ranking (SBFL, G-01) would reach them, but SBFL is out of scope for this plan (section 1); revisit after M5.
- [x] Rerun after both ([v3](../eval/results/claude-haiku-4-5-bugsinpy-v3.json)): 1 of 12 fixed. 1 of 27 attempts did not apply (was 15 of 19); 7 reached the tests and failed; 13 returned no edits because the model could not see the cause.
- [x] Show the full assertion difference: before the first fix attempt the target tests are rerun alone with `pytest -vv`, and the failures section goes in the prompt, with a huge value printout skipped so the diff fits.
- [x] Rerun after it ([v4](../eval/results/claude-haiku-4-5-bugsinpy-v4.json)): 5 of 12 fixed, $0.32. Reviewed by hand: 3 match the project's fix, 1 takes another plausible route, 1 (tornado-1) is doubtful.
- [x] Validate the held-out sets of the fixed cases (`measure.py --validate`): **0 of 5 valid**. Each is the failing test file itself, all of whose tests already ran in the failing run, so passing it proves nothing beyond the target tests. False "verified" stays judged by hand until the next item is done.
- [ ] Independent held-out tests for the 5 fixed cases: tests a wrong fix would fail (e.g. tornado-1 calling `set_nodelay` on a live connection), checked to pass on the project's fix and fail on the buggy commit.
- [ ] Improve what the model sees (source context, the failing test, the assertion values) and how retries use feedback. Change one thing at a time, measured on the corpus.
- [ ] Grow the corpus to about 30 cases by the same pre-registered rules, adding independent held-out tests where possible.

**Exit (targets, revisited after the first round):** at least a quarter of the fixable cases
genuinely fixed, **zero** false "verified", correct declines unchanged, median cost under
$0.02 per run.

### M4 · Usable by a stranger (weeks 9 to 10)

- [ ] A default install ladder: `requirements*.txt`, else `pyproject.toml` / `setup.py`.
- [ ] A comment on the failing commit when there is no PR (G-08); a clear message on a 403.
- [ ] LICENSE file, release `0.3.0` on PyPI (with the sandbox Dockerfile), Action tag `v1`, Marketplace listing.
- [ ] README quick start that fits on one screen.
- [ ] Follow only the README on three Python repositories CIDRA was not built around, one with `pyproject.toml`. Every question needing the source becomes a fix.

**Exit:** all three trial repositories get a verified fix or a clear diagnosis without help.

### M5 · Comparison (weeks 11 to 12)

Same model, same tasks (BugsInPy corpus + `eval/security_fixtures/`), protocol fixed before running:

| System | What it isolates |
|---|---|
| CIDRA | the full system |
| Plain loop: same model, no reproduction check, no audit gate | what CIDRA's safety layers add |
| One maintained open-source agent (chosen at the time, e.g. SWE-agent, OpenHands or Aider) | how CIDRA compares with what exists |

Reported per system: fix rate, false-fix rate (held-out tests), unsafe actions on the attack
fixtures, cost and time. Published as results files and a README table, including results
that do not favour CIDRA.

**Exit:** the README states, with numbers, where CIDRA is better and where it is not.

## 4. Metrics

| Metric | Measured by | Target |
|---|---|---|
| False "verified" | held-out tests, `eval/measure.py` | 0, always |
| Unsafe action on attack fixtures | security fixtures | 0 |
| Correct declines | corpus out-of-scope cases | all |
| Fix rate, fixable cases | corpus | M3 target, then improving |
| Median cost per run | harness | under $0.02 |
| Trial repositories working from the README alone | M4 | 3 of 3 |

## 5. Budget

Model spend stays under **$20 a month** against a $50 ceiling. A full corpus run costs about
$0.30 today; M3 iteration is budgeted at two full runs a day at most. M5 baselines spend more
tokens per task; estimate them on five cases before a full run.

## 6. How we work

- Every change on a branch, through a pull request, CI green, rebase-merged
  ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- Every bug fix ships with a test that fails on the old code.
- Every requirement and finished milestone item is listed in [requirements.yml](requirements.yml) with
  tests tagged `@pytest.mark.req`; CI fails if any of them has no passing test in the run.
- A change that affects repair results is measured with `eval/measure.py` and its result file committed.
- A gap found and not fixed goes into [KNOWN_GAPS.md](KNOWN_GAPS.md) the same day.
