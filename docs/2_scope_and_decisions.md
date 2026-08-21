# Scope & Decisions — CIDRA (Continuous Integration Debugging and Repair Agent)

> This doc is the contract. Every phase, prompt, and line of sandbox code should trace back
> to a decision made here. If a decision changes mid-build, update this file first, then the
> code — not the other way around.

---

## 0. Positioning (read this before anything else)

**This is not pitched as "an AI that fixes your CI."** That category already exists and is
crowded — OpenHands has a CI-failure resolver, and there are several funded products doing
the same pitch (Optibot's CI Fixer, Dagger's self-healing pipelines, debugg.ai, gitar.ai).
Going head-to-head on "we auto-fix builds" is a weak position: less mature, less tested,
built in two weeks.

**The actual pitch:**

> A reliable, safety-verified failure-repair system for a well-defined set of CI failure
> classes — every proposed fix is proven green in a network-isolated, resource-capped
> sandbox before it's ever suggested, and the system's accuracy and safety are measured,
> not asserted.

The differentiator is not "we fix CI." It's:
1. **Narrow, honest scope** — named failure classes, not "any bug."
2. **Verification as the deliverable** — "proven green," not "LLM guessed."
3. **Measured reliability** — an eval table over a fixture corpus (see §7), not a demo video.
4. **Measured safety** — an adversarial test set proving the sandbox actually contains bad
   output (see §6), not a paragraph asserting "we use Docker."

Point 4 is a real gap in the field, not just marketing: OpenHands' own public material
concedes that flaky tests break its pass/fail feedback loop — it can't tell whether a fix
worked or the test was just flaky. This project treats that exact failure mode as a design
constraint from day one (see §2, flaky-test class) instead of discovering it in week three.

**README and demo lead with the eval table and the adversarial-sandbox results — not with
"look, it opened a PR."** The PR/comment is the artifact; the numbers are the argument.

---

## 1. Deadline & build target

- **Hard deadline:** Razorpay Buildathon, **2026-09-05** (~2 weeks from doc date, 2026-08-21).
- **In scope for submission:** the full pipeline including the live webhook — this is
  committed, not conditional.
- **Risk flag:** two weeks is tight for webhook+live-CI on top of the offline pipeline. If
  time runs out anyway, cut in this order:
  1. Flaky-test class (lowest rank, see §2) → downgrade to "detected, not handled."
  2. PR creation → downgrade to comment-only (already the v1 default, see §4).
  3. Fix-and-verify for the lowest-ranked remaining class → downgrade to diagnosis-only.
  - **Never cut:** the live webhook, sandbox hardening (§6), or the eval table (§7). Those
    three are the committed scope and the pitch.

---

## 2. Failure classes — ranked

All four candidate classes from the understanding doc are in scope, but ranked. Build top to
bottom; if a class isn't reliably working by its checkpoint, it drops to "diagnosis only"
(still counts as a partial win) rather than blocking the classes above it.

| Rank | Class | Detection signal | Fix action | Why this rank |
|---|---|---|---|---|
| 1 | Missing dependency | `ModuleNotFoundError`, `ImportError` | Add package to `requirements.txt`, re-install, re-run | Easiest to detect, easiest to verify, lowest ambiguity |
| 2 | Simple assertion / off-by-one | `AssertionError` with a comparable expected/actual | LLM patches the literal value or boundary in the test/fixture | Requires real LLM code-editing but is narrow and verifiable |
| 3 | Wrong env var / CI config | Missing/incorrect env var referenced in workflow YAML | Edit the CI workflow file (see decision below) | Detectable from log, but touches a different file type (YAML, not source) |
| 4 | Flaky test | Fails, then passes on identical re-run | **No code edit.** Re-run N times (bounded), report non-determinism, quarantine-flag | **Different graph shape** — this is a re-run loop, not an edit-verify cycle. Highest implementation risk; ranked last on purpose. |

**Decision — flaky-test is architecturally distinct.** Do not try to fold it into the same
`fix → verify` node path as the other three. It needs its own conditional edge: reproduce →
(if intermittent across N reproductions) → classify-as-flaky → publish, with no fix-generation
step at all. Get this into `3_architecture.md` explicitly so it isn't discovered mid-Phase-5.

**Decision — language: Python only for v1.** Missing-dependency and fix logic differ
completely between ecosystems (`requirements.txt`/pip vs `package.json`/npm). Node support is
explicitly out of scope, not a silent gap — call this out in the README as a known limitation
and an extension point (the node-based LangGraph architecture is designed so a `detect_ecosystem`
step could route to a Node-specific fixer later, per the "extensible architecture" claim in §8
of the understanding doc).

**Decision — env/config fix target is the CI workflow file** (e.g. `.github/workflows/*.yml`),
not runtime app config (`.env`, settings modules). Reasons:
- Matches the understanding doc's own example (§3.1: "fixable in workflow file").
- The agent already has repo/checkout access to the workflow file as part of reproduction —
  no new capability needed.
- Runtime `.env`/config failures have a different signature (app crashes post-deploy, not
  CI setup failure) and would need a separate detection path — out of scope for v1.

---

## 3. What "done" claims, precisely

The system **diagnoses and proposes verified fixes for four named CI failure classes in
Python repositories**, with every fix proven green in an isolated sandbox before being
surfaced, and with measured accuracy/safety numbers to back the claim.

The system **does not** claim to fix arbitrary bugs, does not claim Node/JS support, and does
not claim unsupervised production use — the sandbox and bounded retries make it *safe to run
automatically*, not *correct on everything it sees*. State this distinction explicitly in the
README; it's the difference between an honest claim and an overclaim that gets punctured in
Q&A.

---

## 4. Output mode

- **v1 (submission target): comment only.** Post diagnosis + verified diff as a comment on
  the commit/PR. Lower risk, still demonstrates the full verify loop.
- **Stretch: PR creation.** Branch + commit + open PR via GitHub API, if comment-only is
  solid with time to spare before Sept 5.
- Rationale: matches the original doc's cut order (PR creation is the first thing to
  downgrade under time pressure) — starting at the downgraded target means it's never a
  last-minute scramble.

---

## 5. Live webhook — committed, sequenced last

Per the understanding doc's own build order: develop and validate the entire pipeline
against **saved logs and replayed payloads first**. Wire the live GitHub webhook
(HMAC verification, async processing, idempotency on `run_id`, ngrok/tunnel for local dev)
**only after** the offline pipeline is reliable end-to-end. This is a sequencing decision,
not a scope hedge — the live webhook is a committed Sept 5 deliverable (§1), built last
because it depends on every earlier piece working, not because it's optional.

---

## 6. Safety — the other half of the pitch

Beyond the hard rules already listed in the understanding doc (§3.4/§6: no `--privileged`,
no Docker socket mount, network off by default, memory/CPU/PID/time caps, always clean up),
this project adds:

**Decision — build an adversarial test set, not just defensive code.** A short, fixed set of
adversarial "fixes" (LLM-plausible but hostile) run through the sandbox with expected-contained
outcomes, e.g.:
- A fix that adds a `curl`/network call → expect: fails, no egress (network off).
- A fix that writes outside the repo checkout path → expect: contained to mounted volume.
- A fix that spawns a fork bomb / excessive processes → expect: PID cap kills it, host unaffected.
- A fix that runs past a reasonable time budget → expect: timeout kills the container.

Each case gets a one-line result in the eval doc: attack → expected containment → observed
result. This table is short to build (a handful of hours) and is disproportionately valuable
as a "here's the thing nobody else shows publicly" artifact — OpenHands and the commercial CI
fixers don't publish anything like it.

---

## 7. Evaluation — the primary artifact

**Decision — evaluation is a first-class deliverable, tracked from Phase 1, not bolted on
at the end.** Build the fixture corpus (`5_fixtures.md`, one broken commit + saved log per
failure class, per rank in §2) before writing the analysis node, and re-run the full eval
table after every meaningful change.

Eval table shape (fill in as fixtures are added):

| Failure class | # fixtures | Correct category (%) | Reproduced red (%) | Verified green (%) | False "fixed" claims |
|---|---|---|---|---|---|
| Missing dependency | | | | | |
| Assertion/off-by-one | | | | | |
| Env/config | | | | | |
| Flaky test | | | | | |

Target thresholds (adjust once real numbers exist, but set a bar now so "done" is objective):
- Correct category ≥ 90% across all fixtures.
- Verified-green rate = 100% for any class claimed as "fix supported" in the README — if a
  class doesn't hit 100% on its own fixtures, downgrade its README claim to "diagnosis only"
  for that class rather than reporting a partial number as a success.
- Zero false "fixed" claims — a fix that isn't actually verified green must never be reported
  as fixed. This is a correctness invariant, not a target to approach.

---

## 8. LLM provider

**Decision — Anthropic Claude (Messages API), structured JSON output, Pydantic-validated.**
Rationale: strong native structured-output/tool-use support, which is exactly what §3.3 of
the understanding doc requires (JSON that drives graph routing, not prose). This is an
environment-variable-level choice, not an architectural fork — swapping providers later
means changing the model client, not the graph.

---

## 9. Prior art (cite explicitly in README)

State these by name rather than let a reviewer assume you didn't know they existed:

- **OpenHands** — general-purpose open-source coding agent with a CI-failure resolver mode;
  broad scope, and its own material flags the flaky-test/non-determinism problem as
  unsolved for its feedback loop.
- **Optibot CI Fixer, Dagger self-healing pipelines, debugg.ai, gitar.ai** — commercial
  "auto-fix CI" products with the same broad "fix your build" pitch.

This project's stated difference: narrower scope, verification-first design, and published
reliability/safety numbers instead of a general capability claim.

---

## 10. Open items carried into later docs

- Exact `DebugState` schema, node list, and the flaky-test conditional-edge shape →
  `3_architecture.md`.
- Phase breakdown with the fixture corpus built before the analysis node →
  `4_phases.md`.
- Fixture corpus spec (one broken commit + log per class, ranked per §2) → `5_fixtures.md`.
- Sandbox flags, base image, and the adversarial test set from §6 → `6_sandbox_spec.md`.
- Prompt/schema versioning → `7_prompts.md`.
- Webhook payload shape, HMAC steps, idempotency record → `8_api_contracts.md`.
