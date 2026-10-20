# CIDRA Roadmap

**Written:** 2026-10-15 · **Horizon:** about 15 weeks (M6 added 2026-10-19) · **Owner:** Abhishek Kokadwar

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

**Out of scope for this plan:** languages other than Python, webhook mode beyond what
exists, SBFL, the semantic fix cache, and merging without a human. The dashboard was out
of scope until 2026-10-19, when it was brought up to the same standard as the rest: it
shows only real results, and it is tested in CI by component and browser tests. Making it
run and control CIDRA is milestone M6.

## 2. Where it stands (2026-10-19)

| Requirement | Status |
|---|---|
| 1. Authenticate the incoming event | Done: GitHub triggers the Action; webhook mode checks the HMAC |
| 2. Get the failing commit without exposing secrets to its code | Done: Action mode, `cidra fix` (sandboxed first run) and webhook mode (fetches the commit itself) |
| 3. Reproduce the original failure | Done: the CI log's failing tests must fail in the sandbox, twice for a failure CIDRA would patch (G-16, G-17 closed) |
| 4. Generate a patch | 6 of 24 fixable BugsInPy bugs verified (v6, 40 cases); held-out tests show 4 of CIDRA's 9 verified claims are wrong |
| 5. Reject test-weakening or unsafe patches | Done: a test file may change only in its asserts' expected values (G-22 closed) |
| 6. Apply to a clean copy and rerun | Done (G-15 fixed) |
| 7. Original failure fixed, no unrelated regressions | Done: the CI's failing tests must pass and no test may go from passing to failing; tests already failing are listed, not blocking |
| 8. Draft PR with evidence of what was tested | Done (M2): commit, image digest, commands, per-test before/after, audit verdict, dependency changes, model cost, and a rerun command |

## 3. Milestones

Each milestone ends when its exit criteria hold **and are checked by tests in CI**: its items are in
[requirements.yml](requirements.yml), so the requirements check fails if one loses its passing test.

**Order, as it actually went:** M1 was mostly done when the first real-bug run showed 0 of 12
fixed, so M3's fix-rate work was pulled forward and its target met (5 of 12, 4 genuine on
review). M1 and M2 are complete.

### M1 · Trustworthy "verified" (weeks 1 to 3)

- [x] Run the 15 sandbox safety tests in CI (they skip on a practice-repo check they do not need).
- [x] Record per-test results (pytest JUnit XML) before and after the patch: every sandbox test run asks pytest for a report, read whole from the container; kept as `repro_junit` / `verify_junit` and in `measure.py` results (`tests_before` / `tests_after`). Since 2026-10-19 the pass/fail judgement reads the report too, and the log only when there is none (G-25).
- [x] G-17: the test the CI log names must be among the sandbox's failures, or the run is "not reproduced".
- [x] No regressions: verified means the target test went red to green **and** no test went green to red. Tests already failing before the patch do not block a verification but are listed.
- [x] G-22: on an `assertion_error` fix, the failing test file may change only in assert expected values.
- [x] G-16: reproduce at least twice for every fixable category; a disagreement means flaky.
- [x] G-18: an install failure or a non-reproduction says why, and points to `install_command` / `test_command`.
- [x] An end-to-end test in CI: the full graph runs on the 7 practice fixtures with the stub model (`measure.py --stub --check` in the pipeline job), and each must reach its expected outcome, covering `verified_fix`, `diagnosis_only` and `flaky_detected`.
- [x] The adversarial and security suites run in CI (G-05).

**Exit:** each item above has a CI test that fails on the old behaviour.

### M2 · Evidence in every pull request (weeks 4 to 5)

Each draft PR and job summary carries a short, fixed-format evidence block:

- [x] Failing commit (the patch is made against it), sandbox image and digest, Python version.
- [x] The install and test commands, exactly as run.
- [x] Per-test before/after table: target test(s) red to green, counts for the rest, any test that was already failing.
- [x] Audit gate verdict and any surfaced dependency change.
- [x] Model, requests, tokens and cost of the run: tokens times `CIDRA_PRICE_IN`/`OUT`, else a list price for a model CIDRA knows, labelled with its source; no cost rather than a guess.
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
- [x] Independent held-out tests for the 5 fixed cases: tests a wrong fix would fail (e.g. tornado-1 calling `set_nodelay` on a live connection), checked to pass on the project's fix and fail on the buggy commit. All 5 sets are valid (`measure.py --validate`), and all 5 of the v4 patches pass them: **0 of 5 false "verified"** ([result](../eval/results/claude-haiku-4-5-bugsinpy-v4-held-out.json), `measure.py --rejudge`).
- [x] Make runs repeatable: the model is called at temperature 0 (v6); at 1.0 the same log was diagnosed differently between runs.
- [ ] **Bring false "verified" to zero.** v6 ([judged](../eval/results/claude-haiku-4-5-bugsinpy-v6-held-out.json)): 4 of 9 verified fixes fail held-out tests. They delete an error check (tornado-3), widen the change beyond the failing test (thefuck-25), rewrite more than asked (tornado-9), or leave a sibling path broken (youtube-dl-6). Candidate changes, one at a time, measured on the corpus and rejudged: ~~refuse a patch that deletes a `raise`~~ (done: 4 → 3 of 8, tornado-3 refused, no genuine fix lost; `measure.py --reaudit` replays a gate change on a past run for free); keep a fix inside the function the failing test reaches; decline exceptions as the scope says (3 of the 9 were on bugs CIDRA should decline).
- [ ] Improve what the model sees (source context, the failing test, the assertion values) and how retries use feedback. Change one thing at a time, measured on the corpus.
- [x] Grow the corpus to about 30 cases by the same pre-registered rules, adding independent held-out tests where possible. 40 cases: batch 2 (22 cases) added 2026-10-19 under rules committed before it was built, with the cap raised to 10 per project. Every case CIDRA verifies in v6 has a validated held-out set.

**Exit (targets, revisited after the first round):** at least a quarter of the fixable cases
genuinely fixed, **zero** false "verified", correct declines unchanged, median cost under
$0.02 per run.

### M4 · Usable by a stranger (weeks 9 to 10)

- [x] A default install ladder: `requirements.txt` (plus `requirements-dev.txt`, `requirements-test.txt`, `dev-requirements.txt` or `test-requirements.txt` beside it), else `pyproject.toml` / `setup.py` (with its `test`, `tests`, `testing` or `dev` extra), else nothing. A dev or test requirements file without a `requirements.txt` is not read.
- [x] A comment on the failing commit when there is no PR (G-08); a clear message on a 403.
- [x] LICENSE file, release `0.3.0` on PyPI (with the sandbox Dockerfile), Action tag `v1`, Marketplace listing. (0.3.1 is current; every release's wheel is checked for the Dockerfile before upload.)
- [x] README quick start that fits on one screen.
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

### M6 · The dashboard runs CIDRA (weeks 13 to 15)

Today the dashboard shows what CIDRA did; it cannot make CIDRA do anything. This milestone
makes it a control panel for a local or self-hosted CIDRA. It comes after M4 and M5 because
the Action on GitHub is how most users meet CIDRA; the dashboard serves the ones who run it
themselves (`cidra dashboard`, `cidra serve`).

**Audit (2026-10-19), what is wired today:**

| Part | State |
|---|---|
| Runs list, run detail, evidence panel, pull requests tab | Wired: read live from run history (`/telemetry.json`, `/api/runs`), tested in CI by component and browser tests |
| Models, connection test, PR creation toggle | Wired: saved to `.env` and read by the engine at call time |
| API key and base URL | **Half wired**: saved, and the connection test uses the new values, but `llm.py` copies them at import and caches its client, so runs in the same server keep the old ones until a restart |
| Approve | Records who approved and when; opens nothing (CIDRA never merges, by design) |
| Flakiness runs and threshold, max fix attempts | **Not wired**: saved, but `reproduce.py` and `routers.py` read the values once at import, and `config.py` never reads them from the environment, so they are ignored even after a restart (G-19) |
| Container timeout | **Not wired**: saved and read by nothing (G-19) |
| Orchestrator tab | A scripted demo, labelled as one; nothing runs |
| Starting, watching or cancelling a run | Not possible: runs start only from the terminal (`cidra fix`) or a webhook |
| Runs of the GitHub Action | Not visible: they happen on GitHub's machines and stay there (their telemetry is the G-20 problem) |

**Items:**

- [ ] Every setting the dashboard offers, the API key and base URL included, is one the engine reads at call time, or it is
  removed (closes G-19). A test changes each one through `/api/settings` and checks the
  next run behaves differently.
- [ ] Start a run from the dashboard: repository (URL or local path), commit, and optional
  install and test commands, the same inputs as `cidra fix`. It runs in the background, one
  at a time.
- [ ] Watch it: the run's steps (checkout, install, reproduce, diagnose, fix, audit,
  verify, publish) update as they happen, with the sandbox's output and the cost so far.
- [ ] Cancel it: the sandbox and checkout are removed (the G-23 cleanup path).
- [ ] Act on a result: rerun its verification (`cidra verify`); for a verified fix made with
  PR creation off, open the draft pull request after a human approves. Anything that writes
  to GitHub or spends money asks first.
- [ ] Spend limits shown and set per run (`CIDRA_MAX_LLM_CALLS`, `CIDRA_MAX_LLM_TOKENS`).
- [ ] Runs of the GitHub Action: the Action uploads its run record as a workflow artifact
  (closes G-20); the dashboard lists a repository's recent runs from GitHub with a token.
- [ ] The scripted demo stays only as a labelled tour, or goes.

**Rules:** the server binds to localhost unless a token is set (already true); a run
started from the dashboard is the same graph, sandbox and audit gate as any other run;
each control has a browser test against the real server with the stub model, and an entry
in [requirements.yml](requirements.yml).

**Exit:** a user configures, starts, watches, cancels and acts on a run from the dashboard
alone, and every control is proved by a test to change what the engine does.

## 4. Metrics

| Metric | Measured by | Target |
|---|---|---|
| False "verified" | held-out tests, `eval/measure.py` | 0, always |
| Unsafe action on attack fixtures | security fixtures | 0 |
| Correct declines | corpus out-of-scope cases | all |
| Fix rate, fixable cases | corpus | M3 target, then improving |
| Median cost per run | harness | under $0.02 |
| Trial repositories working from the README alone | M4 | 3 of 3 |
| Dashboard controls proved to change the engine's behaviour | M6 browser and server tests | all |

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
