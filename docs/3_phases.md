# Phased Build Plan — CIDRA (Continuous Integration Debugging and Repair Agent)

> **Not a hackathon project.** The original 2026-09-05 Razorpay Buildathon deadline passed;
> this was not submitted, by choice — the goal shifted to building CIDRA properly and in
> depth rather than to a demo date. There are no deadlines in this plan, only ordering.
>
> One continuous roadmap. **Phases 0–5** are done, **Phase 6** (output + safety artifact) is
> in progress, and **Phases 7–14** are the in-depth build: live webhook, then the research and
> enterprise-moat work (SBFL fault localization, git-worktree parallelization, AST policy
> checks, egress proxies + RAG, multi-language, dashboard, GitLab). Ordering still matters —
> don't start a later phase before its dependencies are solid. The eval table and the safety
> artifacts are what the whole thing rests on ([2_scope_and_decisions.md](2_scope_and_decisions.md)
> §0); coverage and depth come before breadth.

Each phase: **goal → deliverables → exit criteria.** Exit criteria are the only thing that
marks a phase done — not "I wrote the code." (Phases 0–6 retain their original
"what to cut if behind schedule" notes as a record of the trade-offs actually made; from
Phase 7 on there is no schedule to cut against, so those notes are dropped.)

---

## Status as of 2026-09-21

| Phase | State | Evidence |
| --- | --- | --- |
| 0 — Skeleton & toy graph | **done** | graph compiles and terminates; structured output via forced tool call |
| 1 — Fixture corpus | **done** | 7 fixtures, practice repo live at `helpmecode69/cidra-practice` (green `main` + 7 break branches) |
| 2 — Log ingestion + isolation | **done** | `fetch_log` pulls from the Actions API; Tier 1 **7/7** on real CI logs |
| 3 — Root-cause analysis | **done** | Tier 2 **7/7** on real CI logs (`claude-haiku-4.5`) |
| 4 — Docker sandbox | **done** | `test_sandbox.py` **15/15**; `repro_check.py` **8/8** red |
| 5 — Fix + verify loop | **done** | `test_pipeline.py` **6/6** on real Docker; zero false `verified` claims |
| **6 — Output (comment) + safety artifact** | **done** (bar a live-PR comment, a Phase-7 concern) | units 39/39; adversarial **8/8 contained**; `test_pipeline` 6/6, `test_sandbox` 15/15 on real Docker |
| 7 — Live webhook integration | **code done** (live engine run pending Docker + write token) | server 7.1–7.6 + replay tooling; 35/35 webhook+replay units; drive it via `scripts/replay_delivery.py` |
| 8 — SBFL fault localization + flake filtration | **done** (live coverage collection pending Docker) | flakiness score + SBFL + bias eval; 22/22 Phase-8 units; SBFL top-1 100% vs 24% baseline under shuffling |
| 9 — PR scaffolding + git-worktree parallelization | **code done** (live PR POST pending LLM+token) | `git_ops.py` + `checkout.py` + `pr.py`; 28/28 Phase-9 units; SEC-04 PASS; pipeline 6/6 on Docker |
| 10 — AST-level static policy checks | **done** | `cidra/nodes/audit.py`; `test_audit.py` 14/14; SEC-07 now PASS (SR-13/14/15) |
| 11 — Egress proxy + vector-RAG of past failures | **fix-cache done** (egress + embeddings deferred) | fingerprint + verified-fix cache; 22/22 units; cache hit → 0 LLM calls; egress→G-12, embeddings→G-13 |
| 12 — Multi-language generalization (Node/JS) | planned | detailed below |
| 13 — Fleet TUI + web dashboard (HITL gate) | **In Progress** (TUI done; React dashboard + HITL gate active) | `history.py` + `tui.py`; 11/11 units; `python -m cidra.tui`; web/live active |
| 14 — GitLab CI/CD support | planned | detailed below |

**Threat & security docs now exist** ([threat/](threat/), [../eval/security_fixtures/](../eval/security_fixtures/)).
Several later phases exist partly to satisfy requirements written there: Phase 10 implements
SR-13/SR-14 (patch guards), Phase 11 implements SR-09 / SEC-03 (egress), and Phase 9's git
handling must satisfy SR-16/SR-17 (hardened git, no foreign `.git`). Each such phase names its
requirements in its exit criteria.

**Test suite** (organized under `tests/`, see [../tests/README.md](../tests/README.md)):
`pytest -m "not docker"` → **172 passed**; `tests/integration/` (21, Docker) runs with the
daemon up. Layout: `tests/unit/` (pure/fast), `tests/server/` (Phase 7 webhook), `tests/integration/`
(sandbox + pipeline, auto-marked `docker`).

Separate eval harnesses (not pytest): `eval/run_eval.py` (Tier 1/2 7/7), `eval/repro_check.py`
(8/8 red), `eval/adversarial/run_adversarial.py` (ADV-01..08 **8/8 contained**),
`eval/security_fixtures/run_benchmark.py` (**SEC-01/04/06/07 PASS**, 4/8 resolved),
`eval/sbfl_bias_eval.py` (SBFL top-1 **100%** vs 24% baseline under shuffling).

`repro_check` runs 8 checks over 7 fixtures and F-04 is the flaky one, so an occasional
7/8 is the fixture working as designed, not a regression — that is the whole point of F-04.

**Known gaps** are tracked in one place: [KNOWN_GAPS.md](KNOWN_GAPS.md) — every built-but-not-
yet-fully-proven item and every deferred one, each with what unblocks it and how we'll know
it's closed. The load-bearing ones right now: live SBFL collection (G-01, Docker), full engine
live run (G-02, Docker+credits), draft-PR/comment live POST (G-03/G-04, credits+token).

---

## Phases 0–6 — Core engine (done, except 6)

> These were built under the original hackathon schedule. The "if behind schedule" notes are
> kept verbatim as a record of the trade-offs that were actually on the table at the time.

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
- [x] Toy graph runs via one command and prints state after each node.
- [x] One Pydantic-validated structured JSON response received from Claude. *(via OpenRouter, forced tool call)*

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
- [x] At least 1 fixture for rank-1 and rank-2 classes exist with saved logs + expected JSON. *(7 fixtures: F-01, F-01b, F-02, F-02b, F-03, F-04, N-01)*
- [x] Rank-3 and rank-4 fixtures exist at minimum as broken commits (logs can follow in Phase 2). *(all 7 have real `raw.log` from GitHub Actions, captured in Phase 2)*

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
- [x] For every fixture log, the isolated region visibly contains the actual error (manually
      verified once, then locked in as a regression check). *(Tier 1 7/7 against real CI logs; `test_github.py` 9/9)*
- [x] No RAG/embeddings — confirmed unnecessary per the understanding doc §6.

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
- [x] Correct `category` on 100% of rank-1/2 fixtures, best-effort on rank-3/4. *(Tier 2 7/7 on real CI logs, `anthropic/claude-haiku-4.5`)*
- [x] Malformed JSON never crashes the graph — always resolves to either a valid retry or a
      clean "diagnosis failed" state. *(forced tool call + bounded retry; `test_analysis_retries_then_gives_up`)*

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
- [x] Every Phase 1 fixture reproduces **red** (the original failure) in the sandbox.
      *(`eval/repro_check.py` 8/8. Two caveats: F-04 is flaky by construction, so it
      intermittently reports 7/8 — expected. And F-03 reproduces red here only because
      `repro_check` runs without `ci_env`; inside the full pipeline, which supplies
      `API_TOKEN`, it does not reproduce at all — see Phase 5.)*
- [x] Confirmed via `docker ps`/`docker volume ls` after a run: nothing left behind. *(`test_container_is_removed`)*
- [x] At least 2 of the 4 adversarial cases from §6 tested and contained (full set can finish
      in Phase 6). *(`test_sandbox.py` 15/15: no network, no docker socket, no host secrets, pids limit holds, timeout kills)*

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
- [x] Rank-1 fixture: verified green 100%. *(F-01 → `verified_fix`, real Docker)*
- [x] Rank-2 fixture: verified green on at least the built fixture(s). *(F-02 path proven; `patch_source` strategy live)*
- [x] Rank-3: at least diagnosis-correct; green if time allows. *(diagnosis correct. Deliberately NOT green — see the env_config note below)*
- [x] Flaky-test: correctly classified as flaky (not "fixed") on its fixture. *(F-04 → `flaky_detected`, 0 fix attempts)*
- [x] Zero false "verified" claims anywhere (hard invariant from §7 — check this explicitly). *(`test_pipeline.py` 6/6: an unappliable patch yields `verified: False`; N-01 and F-03 never claim a fix)*

**Rank-3 (`env_config_error`) is deliberately diagnosis-only.** This is the "downgrade rather
than ship an unverified fix" clause below, exercised on purpose rather than under time
pressure. The break lives in `.github/workflows/ci.yml`, and nothing in the pipeline reads
that file — the sandbox takes its environment from `ci_env` and invokes `pytest` directly. So
an env-config failure neither reproduces in the sandbox (the harness supplies the very
variable the break removed) nor could have a patch verified if it did. `env_config_error` is
therefore absent from `STRATEGIES`: `select_strategy` returns `None`, routing straight to the
report with **0 LLM calls**. Analysis still classifies it correctly; only the repair path is
out of scope. Real support (parse the workflow's `env:` block, inject it into the sandbox,
prove red-without / green-with) is **Option C** in
[4_architecture.md](4_architecture.md) §5.1, deferred until workflow fixes need to reach a PR.

If behind schedule: downgrade the lowest-ranked class still failing to diagnosis-only rather
than shipping an unverified "fix." This is the §7 invariant — never compromise it for scope.

---

### Phase 6 — Output (comment) + safety artifact
**Goal:** close the loop with a real, honest output, and finish the adversarial safety table.

Broken into steps, each with its own validation. Steps 6.1–6.3 and 6.5 are done and unit-green;
6.4 (harness) is built and runs on a Docker host; 6.6 gates on that run.

| Step | What | State | Validation |
|---|---|---|---|
| 6.1 | `render_comment` — honest Markdown body; SR-12 (named fields, capped model prose); never claims an unverified fix | **done** | `test_report.py` 7/7 |
| 6.2 | `github_write.py` — write-token module, separate from read-only `github.py` (SR-06); idempotent post-or-update via a hidden marker | **done** | `test_github_write.py` 5/5 |
| 6.3 | `publish` node wired — renders, posts when a PR + write token exist, dry-runs otherwise (every fixture run) | **done** | `test_publish.py` 4/4 |
| 6.4 | Adversarial harness — ADV-01..08 through the real runner, host-side containment checks, SKIP (never faked) without Docker | **done — 8/8 contained** | `run_adversarial.py`; §8 table recorded 2026-09-08 |
| 6.5 | Optimization — removed a dead `final_output` write (two nodes owning one field); fixed a comment-pagination bug that broke idempotency on busy PRs | **done** | covered by 6.1–6.3 tests |
| 6.6 | Full regression + docs — §8 table filled from a Docker run, engine E2E re-verified | **done** | `test_sandbox` 15/15, `test_pipeline` 6/6, `repro_check` 8/8, units 39/39 |

Deliverables:
- GitHub comment posting (diagnosis + verified diff) via the write-scoped fine-grained token,
  separate module from the read path (threat-model Rule 1).
- Runnable adversarial harness recording ADV-01..08 into `6_sandbox_spec.md` §8.
- Eval table finalized for the core-engine scope (Phases 0–6).

Exit criteria:
- [x] Comment composition + write path implemented and unit-verified (16/16 across 6.1–6.3, 6.5).
- [x] Full adversarial table (attack → expected → observed) recorded in `6_sandbox_spec.md`
      — **8/8 contained** on `cidra-sandbox:base`, 2026-09-08, 0 leaked containers.
- [x] Engine re-verified E2E on real Docker: `test_pipeline.py` 6/6 through the new publish
      node, `test_sandbox.py` 15/15, `repro_check.py` 8/8.
- [ ] A real comment posted on the practice repo for one fixture per handled class *(needs a
      live PR + write token — the publish path is done and dry-runs without them; this lands
      naturally in Phase 7 when the webhook supplies `issue_number`)*.

**One item open**, blocked only on a live PR + write token, not on code. Everything mechanical
is done and verified on real Docker.

---

### Phase 7 — Live webhook integration
**Goal:** a live, asynchronous GitHub Actions failure triggers the CIDRA engine
automatically, no human in the loop to start it. This is the phase that finishes Phase 6's one
open item — the webhook supplies `issue_number`, so the already-built publish path posts a real
comment. Built after the core engine because it depends on every prior phase being solid.

**Deployment model — BYOK.** CIDRA runs Bring-Your-Own-Key: the operator supplies
`CIDRA_API_KEY` + `CIDRA_BASE_URL` (any OpenAI-compatible endpoint) and the two GitHub PATs via
environment, exactly as [FixSense does](../docs/research/Research_CI_Agent_Security.md) (§7).
No key is ever committed or stored by CIDRA. The keys used in development are test keys supplied
the same way. BYOK needs **no new code** — config already reads every credential from env — but
it sets a hard constraint on this phase: the webhook process is Zone 4 (holds the keys); the
sandbox container is Zone 3 (SR-08: no key ever enters it); and the signature-verifying receiver
must never hand the write token to the code path that ingests an untrusted payload (SR-06).

Broken into steps, each independently testable. The graph already accepts `{repo, run_id, …}`
and derives the rest, so Phase 7 is a trigger surface in front of an engine that is done.

| Step | What | Deliverable | State / Validation |
|---|---|---|---|
| 7.1 | **HMAC-SHA256 verification** — reject any payload whose `X-Hub-Signature-256` fails against `CIDRA_WEBHOOK_SECRET`, before parsing (Zone-1, [4_architecture.md](4_architecture.md) §2). Constant-time. | `cidra/server/security.py` | **done** — `test_webhook_security.py` 7/7 |
| 7.2 | **Idempotency store** — SQLite keyed on `(run_id, commit_sha)`; `claim()` False on a seen key; survives restart. | `cidra/server/idempotency.py` | **done** — `test_idempotency.py` 4/4 |
| 7.3 | **Event parse + filter** — only `workflow_run.completed` + `conclusion=="failure"`; extract `repo`/`run_id`/`head_sha`; resolve PR via `pull_requests[]`, else SHA lookup on the read-only token; dry-run if none; else 204. | `cidra/server/events.py` | **done** — `test_events.py` 10/10 |
| 7.4 | **FastAPI receiver** — `POST /webhook`: verify → parse → claim → **200**, graph via `BackgroundTasks`. Duplicate → 200 no-op. `GET /` health. Startup refuses without the secret. | `cidra/server/app.py` | **done** — `test_webhook_app.py` 8/8 (incl. sig-before-parse, dup no-op) |
| 7.5 | **Graph dispatch** — worker builds the seed `DebugState` and invokes `build_graph()`; publish now has an `issue_number` → posts for real; exceptions logged, never crash the server. | `cidra/server/worker.py` | **done** — `test_worker.py` 3/3 |
| 7.6 | **Config + docs** — `CIDRA_WEBHOOK_SECRET` + `CIDRA_IDEMPOTENCY_DB` in config/.env.example (fail-loud startup guard); `8_api_contracts.md` written; ngrok/registration documented. | config, `docs/8_api_contracts.md` | **done** — guard verified; doc complete |
| 7.7 | **Live E2E + optimization** — `scripts/replay_delivery.py` drives the full pipeline (real HMAC + graph + Docker + comment) without a tunnel; `--twice` proves idempotency. Optimization: dedupe-before-work; hot path skips the redundant `get_run` (webhook already supplies `commit_sha`). | `scripts/replay_delivery.py` | **replay tooling done** — `test_replay.py` 3/3; full engine run pending Docker up + write token |

**Decisions (locked for this phase):** PR resolution uses `pull_requests[]` then a SHA lookup
for the fork-PR case, dry-running if neither yields a PR. Execution is FastAPI `BackgroundTasks`
in-process — the simplest thing that meets the async-trigger criterion; a durable queue is a
Phase 13 concern, and idempotency + GitHub retries cover a mid-run crash until then.

Exit criteria:
- [x] A payload with an invalid HMAC signature is rejected (401) before any parsing
      (`test_webhook_app.py::test_signature_checked_before_parse`, and confirmed live —
      wrong secret → 401).
- [x] A duplicate delivery (same `run_id` + `commit_sha`) terminates with a clean `200 OK`
      no-op — no second dispatch (`test_duplicate_delivery_is_noop`, **and confirmed live**:
      a re-delivery after a server restart logged `duplicate delivery … no-op`, proving the
      SQLite claim survived the restart).
- [x] `8_api_contracts.md` complete.
- [x] **Live webhook path proven** (2026-09-13) via `scripts/replay_delivery.py` against a
      real failed run: HMAC verified → event parsed → claimed → 200 returned → background
      `dispatch`→`done` logged → real CI log fetched from GitHub. 0 leaked containers.
- [ ] **Full engine leg (LLM → sandbox → comment) unrun** — the analysis call returns
      OpenRouter `402: insufficient credits`, which the pipeline correctly handles as
      `outcome=failed` (no false claim). Blocked on LLM budget on the BYOK key, not on code;
      same gap already noted for the eval comparison. A real *posted* comment additionally
      needs an open PR on the target branch (the practice-repo fixtures are branch pushes,
      `pull_requests=[]`, so publish dry-runs by design).

---

## Phases 8–14 — In-depth build (research, enterprise, moat)

> This is the reason the project continued past the hackathon: the depth that a demo date
> could not have accommodated. Each phase carries its own research or enterprise value, noted
> per phase. Sequence is a recommendation, not a lock — re-confirm dependencies before starting
> one. Every new failure class or capability still earns an eval-table row before it is claimed
> as supported (the §7 invariant), and every phase that touches the threat model names its
> requirements.

### Phase 8 — Advanced fault localization + flake filtration
**Goal:** remove LLM fault-localization bias, and keep flaky tests out of the repair queue
entirely. *(Research value: the methodology section of a paper — SBFL + LLM beats
prompt-only localization.)*

Built in steps, each unit-verified:

| Step | What | State / Validation |
|---|---|---|
| 8.1 | **Deterministic Flakiness Score (0–100)** ([reproduce.py](../cidra/nodes/reproduce.py) `flakiness_score`) — `round(100·(1−\|pass−fail\|/n))`; 0 unanimous, 100 a perfect split. `classify_flakiness` isolates at score ≥ threshold → `flaky_detected` → **0 repair attempts**. Generalizes the F-04 binary flip into a measured degree, shown in the comment. | **done** — `tests/unit/test_flakiness.py` 9/9 |
| 8.2 | **SBFL core** ([sbfl.py](../cidra/nodes/sbfl.py)) — Ochiai + Tarantula over a coverage spectrum; `rank()` is deterministic and **input-order-independent** (ties break on name). | **done** — `tests/unit/test_sbfl.py` 8/8 |
| 8.3 | **Coverage collection** ([localize.py](../cidra/nodes/localize.py)) — a pytest plugin records per-test line coverage in the sandbox, builds the spectrum, ranks it, and feeds the ranking into the **fix** prompt as `<fault_localization>` evidence. Best-effort: needs coverage+pytest in the session, degrades to no-evidence otherwise (no image change). | **done (unit)** — `tests/unit/test_localize.py` 5/5; live collection pending Docker |
| 8.4 | **Order-bias test** — the ranking's #1 is stable across 50–100 shuffles of the input order. | **done** — in `test_sbfl.py` + `eval/sbfl_bias_eval.py` |
| 8.5 | **Eval + docs** — `eval/sbfl_bias_eval.py` measures SBFL vs. a prompt-first baseline under shuffling. | **done** |

Exit criteria:
- [x] Intermittent failures are classified **FLAKY** with **0 repair attempts** generated
      (`test_flakiness.py::test_intermittent_is_flaky_with_zero_repair` — flaky routes straight
      to the report, never to `select_strategy`/`generate_fix`).
- [x] Fault localization identifies the buggy method regardless of input order, verified by
      shuffling and re-running: **SBFL top-1 100%** across scenarios vs. a **24%** prompt-first
      baseline (`eval/sbfl_bias_eval.py`; `test_sbfl.py::test_ranking_is_input_order_independent`).

**Remaining gap (honest):** live SBFL coverage collection inside a container is unit-tested
(parser, degradation, evidence injection) but not yet run end-to-end on Docker — same
Docker-gated status as other integration checks. The math and bias-independence, which are the
phase's actual claim, are fully proven offline.

Also folds in the eval backfill from the old plan: expand the corpus to multiple fixtures per
class and push toward the §7 thresholds (≥90% category accuracy, 100% verified-green for any
fix-supported class) with real statistical confidence, and close any class left diagnosis-only.

### Phase 9 — PR-native scaffolding + git-worktree parallelization
**Goal:** move from posting comments to isolated, parallel branch modification and automated
draft-PR creation. *(Resume/job value: Git internals + GitHub REST API under concurrency.)*

Isolation + hardening done (no LLM needed); PR generation is the one remaining piece (needs a
verified fix, i.e. LLM credits + write token — same gate as 7.7).

| Step | What | State / Validation |
|---|---|---|
| 9.1 | **Hardened git wrapper** ([git_ops.py](../cidra/git_ops.py)) — the only module that shells to git; every call sets `GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_GLOBAL=/dev/null`, `protocol.file.allow=never`, `core.hooksPath=/dev/null`, empty credential helper, **and neutralizes `core.fsmonitor`/`sshCommand`/`diff.external`/pager/editor** (SR-16). | **done** — `test_git_ops.py` 6/6 |
| 9.2 | **Isolated checkout** ([checkout.py](../cidra/nodes/checkout.py)) — clone into `worktrees/cidra-patch-{run_id}`, checkout the commit, **strip `.git`** (SR-17). file transport allowed only for our own top-level local clone, submodules off. | **done** — `test_checkout.py` 6/6 |
| 9.3 | **Graph wiring** — `checkout_commit` now runs *before* `prepare_sandbox` and feeds it the isolated tree; `cleanup` removes the dir; a failed checkout short-circuits. | **done** — `test_checkout_node.py` 4/4; graph 15/15 |
| 9.4 | **Parallelization** — 10 concurrent checkouts, zero cross-contamination; cleanup of one leaves others intact. | **done** — `test_parallel_checkout.py` 2/2 |
| 9.5 | **SEC-04 live** — real hostile repo (hook + `core.fsmonitor` + alias) driven through the hardened checkout; canary never fires, no `.git` in the tree. | **done** — `test_sec04.py` 3/3; benchmark **SEC-04 PASS** |
| 9.6 | **PR generation** — on a verified fix, build branch `cidra/patch-{run_id}` from the diff (hardened git, applied as data), push it, open a **draft** PR via REST (idempotent, never merges — SR-11). Wired into `publish`; PR failure never sinks the comment; the authenticated PR clone is always cleaned (try/finally). | **code done** — `test_pr.py` 7/7; live POST needs LLM credits + write token |

**SEC-04 caught a real gap.** `core.hooksPath=/dev/null` was not enough: a repo-local
`core.fsmonitor=<cmd>` executes on an ordinary `git status`. The wrapper now overrides fsmonitor
and the other config-based command vectors on every call — verified by the live SEC-04 test.

Exit criteria:
- [x] Multiple parallel repairs isolated on one host with no shared tree / collision
      (`test_parallel_checkout.py`; 10 concurrent, no cross-contamination).
- [x] SR-16/SR-17 hold — SEC-04 canary never fires; no `.git/` reaches the sandbox tree
      (`test_sec04.py`, benchmark SEC-04 PASS). Engine E2E still green on Docker
      (`test_pipeline.py` 6/6 through the reordered checkout→sandbox path).
- [x] CIDRA generates structured **draft** PRs — branch-from-diff + push + draft-PR REST
      path built and unit-verified (`test_pr.py` 7/7): draft only (never merges, SR-11),
      idempotent, best-effort (never sinks the comment). The *live POST* to github.com is the
      only part still gated on LLM credits + write token (same gate as 7.7).

### Phase 10 — AST-level static policy checks
**Goal:** stop the agent "cheating" the test suite — deleting validation, loosening checks, or
disabling safety to force a green build. *(Enterprise moat: statically proving a generated diff
does not weaken security posture — the differentiator over Copilot and Jules.)*

This phase **implements SR-13, SR-14, and SR-15** from
[threat/security_requirements.md](threat/security_requirements.md) and is directly tested by
[SEC-07](../eval/security_fixtures/07_repo_write_abuse/). **No LLM required** — pure static
analysis of the diff the model already produced — which is why it was buildable while the LLM
key was out of credits.

Built as a new graph node `audit_patch` ([cidra/nodes/audit.py](../cidra/nodes/audit.py)) wired
**between `generate_fix` and `apply_patch`**: a rejected diff routes straight to the report
(→ `diagnosis_only`, "no safe fix found") and **never reaches the sandbox**. Each fix-loop retry
is re-audited. The router fails safe — a missing verdict routes to the report, never to apply.

Deliverables (all done):
- **Diff auditing** — `_parse_diff` splits the unified diff per file; removed test code is parsed
  with `ast` to count assertions robustly (regex fallback for non-standalone fragments).
- **Safety invariants, enforced programmatically.** Rejects a patch that:
  - deletes a test / removes more assertions than it adds, or skips/xfails a test (SR-13);
  - weakens a conditional to `if True:` or inserts `verify=False` (SR-13);
  - touches `.github/`, `.cidra/`, CI YAML, `AGENTS.md`/`CLAUDE.md` (SR-14);
  - exceeds the line/file ceiling — 200 lines / 10 files (SR-15).
- **Dependency-pin changes surfaced**, never silently applied — shown as a distinct
  ⚠️ block in the comment ([report.py](../cidra/nodes/report.py)), and rejection reasons are
  spelled out in the diagnosis-only comment (SR-14).
- tree-sitter for non-Python languages is deferred to Phase 12 (multi-language); the Python
  `ast` path covers the current scope.

Exit criteria:
- [x] Patch application **fails** when the LLM deletes/skips a test to get green
      (SEC-07 `delete_test` / `skip_test` → rejected; `test_audit.py`, benchmark SEC-07 PASS).
- [x] CIDRA rejects a security-policy violation and surfaces pin changes
      (SEC-07 `edit_ci_yaml` → rejected; `typosquat_pin` → surfaced). Verified by
      `test_audit.py` 14/14 and `eval/security_fixtures/run_benchmark.py` (SEC-07 fully PASS).

### Phase 11 — Egress proxy + vector-RAG of historical failures
**Goal:** sever outbound exfiltration during untrusted execution, and cache successful fixes to
cut token cost. *(Enterprise/startup value: ~15× token reduction on repetitive failures; EU AI
Act security alignment.)*

Split into two halves. The **fix-cache half is built offline** (no Docker, no API); the
**egress half is deferred** (inherently Docker/network → [KNOWN_GAPS.md](KNOWN_GAPS.md) G-12).

| Step | What | State / Validation |
|---|---|---|
| 11.1 | **Failure fingerprint** ([fingerprint.py](../cidra/nodes/fingerprint.py)) — normalize a traceback (strip line nos, addresses, temp paths, timestamps) → stable SHA256; stable across noise, sensitive to error type/message. | **done** — `tests/unit/test_fingerprint.py` 9/9 |
| 11.2 | **Verified-fix cache** ([fix_cache.py](../cidra/nodes/fix_cache.py)) — JSON store keyed by fingerprint; get/put; corrupt/missing file → miss, never a crash. | **done** — `test_fix_cache.py` 7/7 |
| 11.3 | **Cache check** in `select_strategy` — compute fingerprint, and on a hit set `fix_diff` + `cache_hit`; router skips `generate_fix` (**the LLM**) straight to `audit_patch`. The diff is still audited (SR-13/14) and re-verified in the sandbox — the cache saves the model call, never the verification. | **done** — `test_fix_cache_wiring.py` |
| 11.4 | **Cache write** in `verify_fix` — the sole writer; caches **only** a freshly verified fix, never a cache-hit re-run, never a failure (preserves the no-false-`verified` invariant). | **done** — `test_fix_cache_wiring.py` 6/6 |
| — | **Egress firewall** in the Docker runtime (block outbound DNS/sockets unless declared). | **deferred** — G-12 (Docker) |
| — | **Semantic/embedding RAG** (Chroma) for "similar" failures. | **deferred** — G-13 (needs embedding dep/API); exact match ships the repeat-failure win now |

Exit criteria:
- [x] A repeat of a previously-solved failure reuses the cached fix with **0 LLM calls** — the
      cache hit routes past `generate_fix`; verified by `test_fix_cache_wiring.py`. *(The
      full "<1s" wall-clock also skips analysis; the sandbox re-verify still runs by design, so
      the LLM-skip is the measured win and a false `verified` stays impossible.)*
- [ ] Malicious test code (`curl`, pre-install exfil) blocked **at the socket layer** —
      **deferred to G-12** (egress proxy, Docker). SEC-03/SEC-05 stay PENDING until then.

### Phase 12 — Multi-language generalization (Node/JS, then Go/Rust)
**Goal:** move from a Python-only fixer to a multi-language assistant. Reopens the §2
Python-only decision — treat as a near-fork of the pipeline, not a bolt-on.

Deliverables:
- **Environment auto-detection** — scan the repo root for `package.json`, `go.mod`,
  `Cargo.toml` and route accordingly.
- **Per-language sandbox images** and dynamic verification commands (`pytest` → `jest`/`vitest`
  → `go test`, etc.). Every hardening rule from [6_sandbox_spec.md](../6_sandbox_spec.md)
  applies unchanged per image.
- Node/JS fix strategies (missing dep, assertion) with their own fixtures and eval rows.

Exit criteria:
- [ ] A broken Node.js project triggers detection, runs in a Node sandbox, and passes its
      Jest/Vitest verification loop.

### Phase 13 — Fleet TUI + web dashboard (HITL gate)
**Goal:** full visibility into the agent's traces, container lifecycle, and token spend — and a
proper human-in-the-loop approval surface (the EU AI Act Article 14 obligation from the threat
model, SR-11/SR-20).

The **run-history + TUI are built offline** (no Docker, no API). The live container/token view,
the web dashboard, and the interactive HITL gate are deferred → [KNOWN_GAPS.md](KNOWN_GAPS.md)
G-14.

| Step | What | State / Validation |
|---|---|---|
| 13.1 | **Run-history store** ([history.py](../cidra/history.py)) — one compact JSON summary per run appended as JSONL (outcome, class, flaky score, cache hit, comment/PR url, ts). No secrets/logs/diffs in the index. Corrupt line → skipped, never fatal. | **done** — `tests/unit/test_history.py` |
| 13.2 | **Record on cleanup** — `publish.cleanup` (the one node every terminal path passes through) appends the summary, best-effort. | **done** — `test_history.py` 6/6 |
| 13.3 | **Fleet TUI** ([tui.py](../cidra/tui.py), `python -m cidra.tui [--limit N] [--watch]`) — stdlib-only text table of recent runs + a verified/cached summary line. No curses/`rich` dependency. | **done** — `tests/unit/test_tui.py` 5/5 |
| — | **React web dashboard** + live container/token view. | **In Progress** — Building decision tree + container view |
| — | **Interactive HITL gate** (approve/reject → PR). | **In Progress** — Building approval surface |

Exit criteria:
- [x] Past runs — outcome, failure class, cache reuse, comment/PR — are visible in a terminal
      view (`python -m cidra.tui`), backed by a durable history recorded on every run.
- [ ] Live task/Docker/token view and interactive pause/approve — **deferred to G-14** (web
      dashboard + live GitHub). The SR-20 decision trace as a review surface lands there.

### Phase 14 — Extensible platform validation (GitLab CI/CD)
**Goal:** prove the "Verify, Declare, Confine" engine is platform-agnostic by extending it once,
for real — validating the extensibility claim from the understanding doc §8.

Deliverables:
- **Decouple the VCS adapter layer** — clear interfaces for repo fetch, branch check, comment,
  and PR/MR creation. (Do the extraction here, driven by a real second implementation, rather
  than speculating an abstraction earlier.)
- A **GitLab adapter** implementing those interfaces against GitLab Merge Requests and Webhooks.

Exit criteria:
- [ ] A failing pipeline on a GitLab repo triggers CIDRA, heals the code, and opens an
      automated Merge Request.

---

## Additional failure classes (ongoing, not a numbered phase)

Candidates once the core classes are solid across languages: timeout/hang detection, dependency
version conflicts, lint/type-check failures. Each earns its own fixtures and eval-table row
before being claimed as supported. Slotted opportunistically, most naturally alongside Phase 8
(coverage) or Phase 12 (per-language).

---

## Cross-cutting rules (apply to every phase)

- Every phase's "done" is its exit criteria, not effort spent.
- No phase widens the failure-class claim in README/pitch materials until its eval-table row
  is filled in with real numbers (§7 invariant).
- Sandbox hardening rules (§6) are never loosened to hit a deadline — cut scope instead.
- Re-run the full eval table after any change to prompts, ingestion, or fix logic — it's a
  regression suite, not a one-time report.
