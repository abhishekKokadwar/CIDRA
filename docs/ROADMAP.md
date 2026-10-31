# CIDRA Roadmap

**Written:** 2026-10-15 · **Revised:** 2026-11-01 · **Horizon:** 5 weeks, to 2026-12-06 · **Owner:** Abhishek Kokadwar

This is the working plan. It replaces `PRODUCT_PLAN.md` for deciding what to build next; that
file stays as background. Progress is tracked in pull requests and in
[KNOWN_GAPS.md](KNOWN_GAPS.md).

## 1. Direction

CIDRA is the **trust layer for AI fixes to failing CI**. Something else writes the patch: a
coding agent (Claude Code, Copilot, Aider, OpenHands), a person, or CIDRA's built-in model
loop. CIDRA does not take its word for anything:

> Whatever wrote the patch, CIDRA reproduces the original failure itself, refuses patches
> that weaken tests or silence errors, verifies on a clean copy with no regressions, and
> publishes the evidence with a command that reruns the check. The patch generator never
> holds a GitHub token or a secret: it hands back a diff, and CIDRA decides what counts as
> verified.

**Revision 2026-11-01: the gate is the product.** Verification needs no model and costs
nothing to run. Patch generation is brought by the user: their own coding agent, or their
own API key for the built-in loop. CIDRA spends no model credits of its own, and the
project's API spend is frozen at $0.

Why: an agent that reports "fixed, tests pass" chose the tests and the environment, and its
report is self-graded. In corpus run v8, 3 of 10 patches that passed the failing tests were
wrong (held-out tests). "AI fixes CI" already exists; independent, measured verification
does not.

Three rules keep the claim honest:

- **Safety and usefulness are measured together.** Every safety number is reported next to
  the fix rate.
- **The gate claims only what it is measured to catch.** It refuses weakened tests, deleted
  or swallowed errors, and regressions in tests that exist. It cannot see a wrong fix the
  repository has no test for (G-26); the held-out results say how often that is.
- **No claim without a measurement.** Comparisons with other tools wait for M5.

**Audiences, in order:** real users (developers using an AI agent on a Python repository),
interviewers, research (optional).

**Out of scope for this plan:** languages other than Python, SBFL, the semantic fix cache,
merging without a human, hosting CIDRA as a service, and any paid model runs.

## 2. Where it stands (2026-11-01)

| Requirement | Status |
|---|---|
| 1. Authenticate the incoming event | Done |
| 2. Get the failing commit without exposing secrets to its code | Done |
| 3. Reproduce the original failure | Done (twice for a patchable failure) |
| 4. Generate a patch | Built-in loop: 10 of 24 fixable verified in v8, 7 genuine, 3 wrong (G-26). Agent path: M7 |
| 5. Reject test-weakening or unsafe patches | Done, in the repair pipeline, `cidra verify` and check-PR mode |
| 6. Apply to a clean copy and rerun | Done |
| 7. Original failure fixed, no unrelated regressions | Done |
| 8. Evidence and a rerun command | Done |

**Finished:** M1 (trustworthy "verified"), M2 (evidence in every PR), most of M4 (install
ladder, PyPI 0.3.1, Action `v1`, Marketplace, quick start; 0.3.2 is merged but not
released), M6's settings item (G-19), and the first three items of M7 (#83, #85, #86).

## 3. Milestones

Each milestone ends when its exit criteria hold and are checked by tests in CI
(items listed in [requirements.yml](requirements.yml)).

**Order:** M3 close-out → M8 → M7 → M4 → release. M5 and M6's remaining items are
deferred (section 3.6).

### M3 · Close out (2 days)

- [x] Patches apply, context, full assertion diff, temperature 0, scope from the log, raise
  and swallow rules, corpus of 40 with held-out tests. (History in git and result files.)
- [x] Write the final result honestly in the README and KNOWN_GAPS: **v8, 7 genuine fixes
  of 24, 3 false "verified" that no audit rule catches without refusing real fixes**, with
  the three cases and why (G-26).
- [x] Mark the zero false "verified" target as **not met with the built-in loop**; it
  carries to M7 as a measurement, not a promise.
- [x] No further corpus runs that spend credits. The second run of the same code (v9)
  stopped at 27 of 40 cases when the credit ran out and will not be rerun: v8 is a single
  run.

**Exit:** the README states the v8 numbers, including the misses.

### M8 · Verify any fix, no model needed (week 1 to 2)

The gate as a standalone tool. Zero cost, so anyone can use it today.

- [x] `cidra verify` runs the audit gate (#91). It used to reproduce, apply and verify a
  patch but never audit it, so a test-weakening diff could come out "verified" there.
- [x] `cidra verify` takes a diff from anywhere (#92): `--patch <file>`, stdin, or `--branch <name>`
  (diff of a branch against the failing commit).
- [x] Separate the gate from generation (#94, `gate.check`): one entry point that takes (failing commit, CI log
  or failing test IDs, diff) and returns verdict and evidence. `cidra fix` uses it unchanged;
  the stub pipeline run gives the same results.
- [x] **Action mode: check a fix PR** (`mode: check-pr`, `cidra check-pr`). On a pull request that claims to fix failing CI
  (opened by an agent or a person), CIDRA reproduces the failure on the base commit,
  applies the PR's diff in its sandbox, runs the audit and the verification, and posts the
  evidence as a PR comment and job summary: verified, refused (and why), or not reproduced.
- [x] Safe by construction: the PR's code runs only in the sandbox with no secrets; the
  comment is posted by a separate step that does not run PR code (no
  `pull_request_target` checkout of untrusted code).
- [x] Tests: the adversarial fixtures as PRs (a test-weakening PR, an error-swallowing PR, a
  PR that breaks another test, a genuine fix) each get the right verdict.

**Exit:** on a demo repository, a PR fixing a failing test gets a "verified" comment with
evidence, and a test-weakening PR gets "refused" with the reason, with no model and no key.
**Met 2026-11-01** on [cidra-practice](https://github.com/helpmecode69/cidra-practice): [#10](https://github.com/helpmecode69/cidra-practice/pull/10), a genuine fix, is verified; [#11](https://github.com/helpmecode69/cidra-practice/pull/11), which loosens the assert, is refused, while the repository's own CI passes it.

### M7 · Bring your own agent (week 2 to 3)

A coding agent becomes a patch generator behind the same gate. The user's own agent and
login are used; CIDRA ships no credential.

- [x] A patch-generator interface (#83). The built-in loop moved behind it unchanged; only a
  generator's diff is kept, never its claims.
- [x] The login stays out of the agent's reach (#85). A proxy container holds the model
  credential, an API key or a subscription token (`claude setup-token`), and the agent's
  container reaches only the proxy. A real-Docker test runs hostile code next to the agent
  and shows it cannot read the credential, the endpoint or the internet.
- [x] Claude Code adapter (#86): headless (`claude -p --bare`) in its own container on a copy
  of the checkout, with a timeout and a spend limit; a placeholder key, so no API key is
  billed by mistake. CIDRA computes the diff itself (`git diff`) and ignores the agent's
  claims. Tested with a stub agent, no model.
- [ ] A malicious stub agent (edits a test, swallows an error) is refused by the gate.
- [ ] Diagnosis without a model in agent mode: the scope is read from the log (only failed
  asserts: fix; anything else: decline), so a run needs no API credit.
- [ ] `cidra fix --agent claude-code` (today: `CIDRA_PATCH_GENERATOR=claude-code`).
- [ ] Record what the agent claimed, untrusted, for the metric below.
- [ ] Pilot on 5 BugsInPy cases, chosen and committed before running: 2 the built-in loop
  returned no patch for, 2 of its false "verified" (thefuck-25, tornado-4), 1 it fixed
  genuinely. One case first, to check usage against the subscription limit; the proxy's
  first real-token run is checked there too.
- [ ] Recorded per case: verified or not, held-out result, gate refusals, **agent claimed
  fixed but CIDRA or held-out tests disagreed**, turns and tokens.
- [ ] Results file and README table published either way.

**Exit:** `cidra fix --agent claude-code` runs end to end on a local repository, and the
pilot's numbers are published.

### M4 · Usable by a stranger (week 4)

- [x] Install ladder, G-08 comment, LICENSE, PyPI, Action `v1`, Marketplace, quick start.
- [ ] Follow only the README on three Python repositories CIDRA was not built around, one
  with `pyproject.toml`: Action check-PR mode (M8) on all three, agent mode (M7) on one.
  Every question needing the source becomes a fix.
- [ ] README rewritten around the two ways to use CIDRA: check a fix PR (free), and fix
  with your own agent.

**Exit:** all three repositories get a correct verdict or a clear diagnosis without help.

### Release and demo (week 5)

- [ ] Release `0.4.0`: `cidra verify` with any diff and the audit, check-PR Action mode,
  Claude Code adapter.
- [ ] A public demo repository: a failing test, an agent's fix PR verified, a test-weakening
  PR refused, the evidence in each.
- [ ] A 3-minute demo video and a written walkthrough following the demo script (section 7).
- [ ] Dashboard: read-only views of these runs (already wired); the scripted orchestrator
  demo stays only as a labelled tour, or goes.

**Exit:** a stranger can watch the video, open the demo repository and reproduce the result.

### 3.6 Deferred (needs credits or comes after users)

- **M5 comparison:** CIDRA vs plain loop vs an open-source agent vs agents behind the gate.
  Needs paid runs at scale. Revisit when credits are available; the M7 pilot is the first
  data point.
- **M6 control panel:** starting, watching and cancelling runs from the dashboard, Action
  run history in the dashboard (G-20). Revisit after real users ask for it.
- **More agents** (Aider, OpenHands): add one only if a user asks or M5 needs it.
- **Deeper context for the built-in loop:** dropped; agents explore code themselves.

## 4. Metrics

| Metric | Measured by | Target |
|---|---|---|
| Gate verdicts on adversarial PRs | fixtures as PRs (M8) | all correct |
| Unsafe action on attack fixtures | security fixtures | 0 |
| False "verified" | held-out tests | reported for every generator; 0 is the goal, not yet met (G-26) |
| Agent "fixed" claims rejected by the gate or held-out tests | M7 pilot | reported |
| Correct declines | corpus out-of-scope cases | all |
| Trial repositories working from the README alone | M4 | 3 of 3 |
| API spend | billing | $0 |

## 5. Budget

**API spend: $0.** The built-in loop runs only on a user's own key. The M7 pilot uses the
owner's Claude subscription for personal development, within its usage limits; it is never
used to serve other people's repositories. Paid runs (M5) wait for credits.

## 6. How we work

- Every change on a branch, through a pull request, CI green, rebase-merged.
- Every bug fix ships with a test that fails on the old code.
- Every requirement and finished milestone item is in [requirements.yml](requirements.yml)
  with tests tagged `@pytest.mark.req`; CI fails if any has no passing test.
- A change that affects repair results is measured and its result file committed.
- A gap found and not fixed goes into [KNOWN_GAPS.md](KNOWN_GAPS.md) the same day.

## 7. Demo script (3 minutes)

1. A small Python repository; a commit breaks a test; CI goes red.
2. **Check-PR mode, no model:** a PR that fixes the bug gets CIDRA's "verified" comment:
   failure reproduced, target test red to green, no regressions, rerun command.
3. A second PR "fixes" it by loosening the assert: CIDRA refuses it and says which line.
4. **Agent mode:** `cidra fix --agent claude-code` on the same failure; the agent's diff
   goes through the same gate; draft PR with evidence.
5. The numbers: v8 corpus results and the M7 pilot, including the false "verified" cases
   and why the gate cannot see them.
