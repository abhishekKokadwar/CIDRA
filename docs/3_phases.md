# Phased Build Plan — CIDRA (Continuous Integration Debugging and Repair Agent)

> Two horizons. **Phases 0–7** must be done by **2026-09-05** (Razorpay Buildathon), live
> webhook included — this is a committed deliverable, not a stretch goal. **Phases 8+** are
> the full-fledged post-hackathon build — deeper coverage, more classes, dashboard, possibly
> GitLab. Don't start a later phase early just because you have time; the eval table and
> safety artifacts from the hackathon phases are what the whole pitch rests on (see
> [2_scope_and_decisions.md](2_scope_and_decisions.md) §0) — polish those before adding scope.

Each phase: **goal → deliverables → exit criteria → what to cut if behind schedule.**
Exit criteria are the only thing that marks a phase done — not "I wrote the code."

---

## Horizon 1 — Hackathon build (by 2026-09-05)

### Phase 0 — Skeleton & toy graph
**Goal:** stop treating LangGraph as abstract; get the plumbing working end to end on a
trivial example before any real logic exists.

Deliverables:
- Repo structure, dependency management (`uv`/`poetry`/`pip` — pick one), config/env loading.
- A trivial 3-node LangGraph (`node_a → node_b → node_c`) with a typed state object that
  actually mutates and can be printed/inspected at each step.
- Anthropic API client wired up with one throwaway structured-output call, validated with
  Pydantic (proves the §8 decision works before it's load-bearing).

Exit criteria:
- [ ] Toy graph runs via one command and prints state after each node.
- [ ] One Pydantic-validated structured JSON response received from Claude.

If behind schedule: this phase cannot be cut — everything depends on it. Keep it to a few hours.

---

### Phase 1 — Fixture corpus (build before any real pipeline logic)
**Goal:** an offline dev loop. Per [2_scope_and_decisions.md](2_scope_and_decisions.md) §2 and
§7, the eval table is the primary deliverable — it needs fixtures to eval against, so this
comes before ingestion/analysis, not after.

Deliverables:
- A dedicated practice repo (Python) with one intentionally broken commit per failure class,
  ranked order: missing-dependency → assertion/off-by-one → env/config → flaky-test.
- Saved raw CI logs for each broken commit (captured once, reused forever — free, instant,
  offline).
- `5_fixtures.md` populated: commit SHA, failure class, saved log path, and the *expected*
  analysis JSON (hand-written ground truth) for each fixture.

Exit criteria:
- [ ] At least 1 fixture for rank-1 and rank-2 classes exist with saved logs + expected JSON.
- [ ] Rank-3 and rank-4 fixtures exist at minimum as broken commits (logs can follow in Phase 2).

If behind schedule: don't cut this — cut fixture *count* (1 per class instead of 2-3), not the
phase itself. Everything downstream needs it.

---

### Phase 2 — Log ingestion + isolation
**Goal:** turn a 10k-line noisy log into the ~50-200 relevant lines, deterministically.

Deliverables:
- Noise stripping (ANSI codes, carriage-return progress bars, timestamps).
- Keyword/regex anchor isolation (`Traceback`, `Error`, `FAILED`, `assert`, `Exception`,
  exit codes) with a window around each hit.
- Runs against every Phase 1 fixture.

Exit criteria:
- [ ] For every fixture log, the isolated region visibly contains the actual error (manually
      verified once, then locked in as a regression check).
- [ ] No RAG/embeddings — confirmed unnecessary per the understanding doc §6.

If behind schedule: this is cheap and central — don't cut, but don't gold-plate either
(no need for adaptive window sizing; fixed windows are fine).

---

### Phase 3 — Root-cause analysis node (LLM)
**Goal:** structured JSON diagnosis that can drive graph routing.

Deliverables:
- System prompt + JSON schema (`category`, `confidence`, `file`, `evidence`, `proposed_action`).
- Pydantic validation with a retry-on-malformed-JSON path (bounded, e.g. 1 retry).
- `7_prompts.md`: prompt version log, few-shot examples drawn from Phase 1 fixtures.
- First real eval table entries: correct-category % per class, run against all fixtures.

Exit criteria:
- [ ] Correct `category` on 100% of rank-1/2 fixtures, best-effort on rank-3/4.
- [ ] Malformed JSON never crashes the graph — always resolves to either a valid retry or a
      clean "diagnosis failed" state.

If behind schedule: don't cut — this is the node that makes the rest of the graph legible.

---

### Phase 4 — Docker sandbox (harden first, use second)
**Goal:** reproduce the failure in a throwaway, contained environment. This is the highest
blast-radius component — build the safety rules in from the start, not as a retrofit.

Deliverables:
- Base Docker image with the common Python toolchain (pip, pytest).
- Sandbox runner via the `docker` SDK: checkout commit → install deps → run failing test →
  capture pass/fail + output.
- Hard rules enforced from commit one (per [2_scope_and_decisions.md](2_scope_and_decisions.md)
  §6 and the understanding doc §3.4): no `--privileged`, no Docker-socket mount, network off
  by default (only on for the install step), memory/CPU/PID/time caps, try/finally cleanup.
- `6_sandbox_spec.md`: exact flags, image contents, lifecycle, threat-model table.

Exit criteria:
- [ ] Every Phase 1 fixture reproduces **red** (the original failure) in the sandbox.
- [ ] Confirmed via `docker ps`/`docker volume ls` after a run: nothing left behind.
- [ ] At least 2 of the 4 adversarial cases from §6 tested and contained (full set can finish
      in Phase 6).

If behind schedule: do not cut hardening rules to save time. Cut fixture coverage instead
(fewer classes reproduced) before ever loosening a safety rule.

---

### Phase 5 — Fix + verify loop
**Goal:** for ranks 1-3 (skip flaky-test's different shape here — see below), generate a
candidate fix, apply inside the sandbox, re-run, confirm green.

Deliverables:
- Fix-generation prompts per class (add-dependency, patch-assertion, edit-workflow-yaml).
- Apply-fix → re-run → verify, bounded retry (cap 3) feeding the new error back on failure.
- **Flaky-test class handled separately in this same phase**, per its own graph shape (see
  [2_scope_and_decisions.md](2_scope_and_decisions.md) §2): reproduce N times, no fix
  generation, classify intermittent as flaky, route straight to publish.
- Eval table updated: reproduced-red %, verified-green % per class.

Exit criteria:
- [ ] Rank-1 fixture: verified green 100%.
- [ ] Rank-2 fixture: verified green on at least the built fixture(s).
- [ ] Rank-3: at least diagnosis-correct; green if time allows.
- [ ] Flaky-test: correctly classified as flaky (not "fixed") on its fixture.
- [ ] Zero false "verified" claims anywhere (hard invariant from §7 — check this explicitly).

If behind schedule: downgrade the lowest-ranked class still failing to diagnosis-only rather
than shipping an unverified "fix." This is the §7 invariant — never compromise it for scope.

---

### Phase 6 — Output (comment) + safety artifact
**Goal:** close the loop with a real, honest output, and finish the adversarial safety table.

Deliverables:
- GitHub comment posting (diagnosis + verified diff) via fine-grained token scoped to the
  practice repo only.
- Remaining adversarial cases from §6 run and recorded (all 4 minimum).
- Eval table finalized for Horizon 1 scope.

Exit criteria:
- [ ] A real comment posted on the practice repo for at least one fixture per handled class.
- [ ] Full adversarial table (attack → expected → observed) complete in `6_sandbox_spec.md`.

If behind schedule: comment-only was already the v1 target (§4) — nothing further to downgrade
here except reducing to 1 demo comment instead of one per class.

---

### Phase 7 — Live webhook + demo polish
**Goal:** the "wow" moment — a real CI failure triggers the whole pipeline live. Built last
because it depends on every prior phase being solid, but it is a committed deliverable for
Sept 5, not optional (see §1).

Deliverables:
- FastAPI webhook endpoint: HMAC signature verification, 200-immediately + background
  processing, idempotency on `run_id`.
- ngrok/tunnel for local dev; live GitHub webhook wired to the practice repo.
- README: scoped claim (§3), architecture diagram, eval table, safety table, demo GIF.
- `8_api_contracts.md`: payload shape, verification steps, idempotency record design.

Exit criteria:
- [ ] A live failing CI run on the practice repo triggers the agent end-to-end without manual
      intervention, and a comment appears.
- [ ] Duplicate webhook delivery (simulate a retry) does not double-process.
- [ ] README complete with real numbers, not placeholders.

If behind schedule: cut demo polish (GIF quality, README wording passes) before touching the
live webhook itself — the webhook is committed for Sept 5.

---

## Horizon 2 — Post-hackathon, full-fledged build (starts after 2026-09-05)

These are not scoped in detail yet — sequence and re-plan each one with the same
goal/deliverables/exit-criteria structure when you actually start it, since priorities may
shift once you have hackathon feedback.

### Phase 8 — Harden and backfill eval coverage
- Expand fixture corpus per class (multiple fixtures per class, not just one).
- Push toward the §7 target thresholds properly (≥90% category accuracy, 100% verified-green
  for any class claimed as fix-supported) with real statistical confidence, not one fixture.
- Close any class that was downgraded to diagnosis-only during the hackathon crunch.

### Phase 9 — Pull request creation (the deferred stretch from §4)
- Branch + commit + PR via GitHub API instead of comment-only.
- Re-verify the fix survives being applied via an actual PR diff, not just an in-sandbox patch.

### Phase 10 — Additional failure classes
- Only after Horizon-1 classes are solid. Candidates: timeout/hang detection, dependency
  version conflicts, lint/type-check failures.
- Each new class gets its own fixtures and eval-table row before being claimed as supported.

### Phase 11 — Vector-RAG for "similar past failures" (stretch, per understanding doc §6)
- Chroma-based embedding layer over historical logs — explicitly *not* for isolating the
  current error (regex/heuristics already do that), only for "have we seen this before."

### Phase 12 — Multi-language support (Node/JS)
- Reopens the §2 decision to scope Python-only. Requires an ecosystem-detection routing step
  and a parallel set of fix strategies (`package.json`/npm) — treat as a near-fork of the
  Python pipeline, not a bolt-on.

### Phase 13 — Dashboard / run history
- Small web UI showing past runs, diagnoses, verification outcomes — makes the eval table
  live instead of a static doc.

### Phase 14 — GitLab support
- Second CI provider. Validates the "extensible architecture" claim from the understanding
  doc §8 by actually extending it once, for real.

---

## Cross-cutting rules (apply to every phase, both horizons)

- Every phase's "done" is its exit criteria, not effort spent.
- No phase widens the failure-class claim in README/pitch materials until its eval-table row
  is filled in with real numbers (§7 invariant).
- Sandbox hardening rules (§6) are never loosened to hit a deadline — cut scope instead.
- Re-run the full eval table after any change to prompts, ingestion, or fix logic — it's a
  regression suite, not a one-time report.
