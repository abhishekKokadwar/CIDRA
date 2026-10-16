# Known Gaps — CIDRA

> The honest list. Everything built-but-not-yet-fully-proven, or deliberately deferred,
> lives here so it is revisited rather than forgotten. Each gap says what's missing, why,
> what unblocks it, and how we'll know it's closed.
>
> **Blocker legend:** 🐳 needs a running Docker daemon · 🔑 needs LLM credits (OpenRouter)
> · 🌐 needs a write token / live GitHub · 🛠 real code work (not just an environment)
>
> Last reviewed: 2026-10-15, against the code (not the earlier docs).

---

## Open gaps

### G-01 · Live SBFL coverage collection (Phase 8) — 🐳
**What:** `cidra/nodes/localize.py` collects per-test coverage *inside the container* via a
pytest plugin, builds the spectrum, and feeds the SBFL ranking into the fix prompt. The
plugin parser, clean degradation (no coverage/pytest → no-evidence), and evidence injection
are unit-tested (`tests/unit/test_localize.py` 5/5). What is **not** yet run end-to-end is the
actual coverage collection in a live sandbox on a real fixture.
**Why open (2026-10-15):** the sandbox image now ships pytest and coverage, so the tools
are there. The likely cause is in the plumbing: the plugin prints the whole spectrum as ONE
`CIDRA_SBFL_JSON=` line at the end of the run, and the sandbox keeps only the last 16,000
bytes of output (`limits.TAIL_BYTES`). Any real suite's spectrum is longer, so the line
loses its prefix and `_parse_blob` finds nothing ("no spectrum collected"). `localize` also
runs `python -m pytest` rather than the configured test command, so a repo that needs
`PYTHONPATH=src` or a test path collects nothing.
**Unblock / fix:** write the spectrum to a file in the container and read it back with
`get_archive`, or `cat` it in a separate step; run it with the configured test command.
**Done when:** an integration test under `tests/integration/` drives `localize` on a real
session and asserts a non-empty ranking whose #1 is the known-buggy element.
**Note:** the SBFL *math* and *order-independence* (the phase's actual claim) are fully proven
offline — this gap is only the live plumbing.

### G-02 · Full engine live run via webhook (Phase 7) — 🐳 🔑 🌐 🛠
**Status 2026-10-05:** the full engine has now run live through the GitHub Action and the
local runner with a real model. The webhook entry point itself is still unproven.
**Update 2026-10-15:** webhook runs now fetch the failing commit from GitHub themselves
(`checkout.fetch_commit`, read-only token passed only through the fetch's environment);
before, they fell back to `CIDRA_PRACTICE_REPO`. Tested against a local stand-in and against
github.com, not yet through a live delivery.
**What:** the webhook path is proven end-to-end *except* the final analysis→sandbox→comment
leg. A real replayed delivery got as far as fetching the CI log, then the LLM call returned
OpenRouter `402: insufficient credits` (correctly handled as `outcome=failed`).
**Unblock / fix:** add OpenRouter credits (or point `CIDRA_BASE_URL`/`CIDRA_API_KEY` at a
funded endpoint) + Docker up. Then
`python scripts/replay_delivery.py --repo helpmecode69/cidra-practice --run-id <RUN_ID>`.
**Done when:** a replayed real failure produces a verified fix and a posted comment, with no
manual command; `--twice` shows the idempotency no-op.

### G-18 · Install failure and non-reproduction are reported as "could not diagnose" — 🛠 (small)
`install_deps` returns `env_ready: False` with no message, and a run that does not reproduce
has a diagnosis but ends `failed`. The report then says "CIDRA could not produce a usable
diagnosis" with no reason. These are the most likely first-run failures on a new repository.
**Fix:** set `analysis_error` from the install output tail, and give `failed`-with-analysis
its own wording that points at `install_command` / `test_command`.

### G-19 · Dead or ignored settings — 🛠 (small)
- Dashboard "Flakiness & Sandbox" fields are saved to `.env` and `config`, but `reproduce.py`
  and `routers.py` imported the constants at load time, so the engine never sees them.
- `CIDRA_ENABLE_RATE_LIMIT_BACKOFF` (set by `action.yml`), `limits.AUTO_REMOVE`,
  `OPENROUTER_API_KEY` / `openrouter_client_1` and the `model` input of `action.yml` are
  read by nothing.
- The fallback model IDs in `llm.py` have not been checked since 2026-10-03.
**Fix:** remove them, or read them at call time.

### G-20 · Public telemetry carries full prompts — 🛠 🌐
`llm.structured` records the full system and user prompt (CI log excerpts and source files)
in the telemetry, and `cidra-bot.yml` commits `telemetry.json` to `main` of a public repo on
every run. **Fix:** upload it as a workflow artifact instead, and stop the commit step.

### G-21 · Release — 🛠 (small)
The 0.2.0 wheel on PyPI has no `sandbox/Dockerfile` (checked 2026-10-15), so a pip install
cannot build its own sandbox; `pyproject.toml` already includes it for the next release.
There is no `LICENSE` file although MIT is declared. The v0.2.0 release title says "Node.js
Support"; Node.js is log parsing only.

---

## Deferred by design (not bugs — scoped out, revisit when the phase arrives)

### G-06 · Security benchmark: SEC-02/03/05/08 still PENDING — 🛠
`run_benchmark.py` shows 4/8 resolved. The rest need nodes from later phases:
SEC-02/03 (secret/network exfil) → Phase 11 egress proxy; SEC-05 (malicious dep) → Phase 11
+ install-step hardening; SEC-08 (instruction confusion) → a prompt-builder guard. Track each
with its phase.

### G-12 · Egress proxy (Phase 11) — 🐳 🛠
The egress-firewall half of Phase 11 (block outbound DNS/sockets from the sandbox unless
declared) is inherently Docker/network and not yet built. The fingerprint fix-cache half IS
built and offline-tested. Closes SEC-03 (network exfil) at the socket layer when done.
**Done when:** a test running `curl`/socket connect in the sandbox is blocked by the proxy,
and the security benchmark's SEC-03 flips to PASS.

### G-13 · Semantic / embedding fix-RAG (Phase 11) — 🔑/🛠
Current cache is **exact** fingerprint match. "Have we seen something *similar*" needs an
embedding model (Chroma + an embedding API or a local model). Deferred; exact match delivers
the repeat-failure token win without a new dependency.
**Done when:** a near-miss failure (same root cause, different message) reuses a cached fix
above a similarity threshold, measured on the fixture corpus.

### G-07 · tree-sitter for non-Python AST checks (Phase 10) — 🛠
`cidra/nodes/audit.py` uses Python `ast`. Non-Python languages (Phase 12 multi-language) need
tree-sitter parsing for the same SR-13/14/15 guards. Deferred until multi-language lands.

### G-08 · Commit-comment fallback for no-PR runs — 🛠 (small)
When a verified/diagnosed run has no PR, `publish` dry-runs. A commit-comment fallback would
make branch-push runs post visibly. Offered earlier, not yet built. Closes part of G-04
without needing a PR.

---

## Documentation debt (carried since earlier phases)

### G-09 · `docs/7_prompts.md` unwritten
A Phase 3 deliverable (prompt version log, few-shot examples). Never written.

### G-10 · `Session` class undocumented in the sandbox spec
`docs/6_sandbox_spec.md` §6 documents only `run_in_sandbox`; the `Session` class that
replaced it for multi-step runs (and now the SBFL collection path) is undocumented.

### G-11 · Model comparison (Haiku vs Sonnet) unrun — 🔑
Eval Tier-2 accuracy has only been measured on one model. Blocked on LLM credits, not code.

---

## Closed (kept for the audit trail)

- **G-05 · Adversarial + benchmark on Docker were point-in-time** — Closed 2026-10-16. CI's
  sandbox tier runs `eval/adversarial/run_adversarial.py` (with a canary secret set, so the
  secret-theft check is not vacuous) and `eval/security_fixtures/run_benchmark.py --tier 2`,
  which now exits 1 on any FAIL. Both gate every PR that changes code.
- **G-22 · A test's setup could be edited to make it pass** — Closed 2026-10-15. A patch may
  change a test file (or a `conftest.py`) only by correcting the expected values of its
  asserts; anything else in it is refused by the audit gate. The fastapi-5 patch is in
  `tests/unit/test_audit_test_edits.py`, which also checks every reference fix in the
  fixtures and the BugsInPy corpus still passes. Kept strict on purpose: a legitimate test
  edit such as renaming a removed `assertEquals` is refused too (benchmark scenario API-04,
  recorded as refused by design); that costs a diagnosis-only report, never a false fix.
- **G-16 · Flakiness was checked only on a "flaky" diagnosis** — Closed 2026-10-15. A failure
  in a category CIDRA patches is now reproduced twice; a green second run, or targets that
  stop failing, end the run as `flaky_detected` with no patch. The 5-run check stays for a
  "flaky" diagnosis. Two runs catch a test that fails half the time only one time in two.
  `tests/unit/test_flaky_every_fixable.py`.
- **G-17 · Reproduction accepted any red run** — Closed 2026-10-15. The failing tests are
  read from the CI log itself (pytest's FAILED / ERROR lines, no model involved) and must fail
  in the sandbox; a different failure ends the run as not reproduced, saying which tests were
  expected and which failed. The diagnosis's `failing_test` stands in only when the log names
  none, and a run with no test ids at all is marked `repro_evidence: exit_code`.
  `tests/unit/test_reproduce_target.py`.
- **G-15 · Fix attempts stacked in the sandbox** — Closed 2026-10-15. `Session` snapshots the
  checkout when it starts and restores it before applying a new diff, and a reinstall replaces
  the installed packages instead of adding to them. What `verify_fix` proves green is now the
  failing commit plus the published diff. `tests/integration/test_session_patches.py` fails on
  the old code. On the real case (BugsInPy fastapi-5) the diff now applies to a clean checkout;
  that run then exposed G-22.
- **G-03 · Draft-PR live POST** — Closed 2026-10-04. A verified fix opened a real draft PR on
  `helpmecode69/cidra-practice` through the GitHub Action, first with a stub model and then
  with a real one (PR #8). A re-run reuses the same PR and refreshes its description; one
  failing commit gets one fix branch. It never merges. The repository must allow Actions to
  create pull requests (README, "Repository setup for pull requests").
- **G-04 · Live PR-thread comment** — Closed 2026-10-04 (stub model). For a failure on an
  existing pull request the fix commit is pushed to that PR's branch, not forced, and one
  comment is posted and then updated on later runs. Not yet repeated with a real model.
- **G-14 · Web dashboard + live view + interactive HITL gate (Phase 13)** — Built React dashboard
  (`dashboard/`) with Command Center, Run Explorer, Ephemeral Container Sandbox & Flakiness Lab (SR-08),
  Pipeline Orchestrator (LangGraph topology), and 4-tab Settings view with live .env synchronization
  and API latency probes. Interactive HITL gate implemented (`/api/runs/{run_id}/approve`) with
  SR-20 raw JSON decision trace accordion (EU AI Act Art. 14). Verified: `tests/server/test_dashboard_api.py`
  (6/6) and `npm run test:wiring` (5/5). (Phase 13)
- **SR-16 was insufficient (fsmonitor bypass)** — `core.hooksPath=/dev/null` alone didn't stop
  a repo-local `core.fsmonitor=<cmd>` running on `git status`. Caught by the live SEC-04 test;
  fixed by also neutralizing `core.fsmonitor`/`sshCommand`/`diff.external`/pager/editor in
  `git_ops.py`. Verified: `tests/unit/test_sec04.py` + benchmark SEC-04 PASS. (Phase 9)
- **PR clone cleanup leak** — an authenticated PR clone lingered if push failed; fixed with
  try/finally in `pr.py`. Verified: 0 leftovers after the suite. (Phase 9.6)
- **Adversarial harness false-green (missing pytest)** — cases passed for the wrong reason;
  rewritten to run hostile code via `python -c`. (Phase 6.4)
- **Benchmark false positive (`/merge` in a comment)** — `no_merge_call` matched prose;
  tightened to real merge calls. (Phase 10)

---

## Stage A Operational Boundaries & Limitations (Empirical Hardening Audit)

1. **Distributed Deadlocks & Complex Concurrency (Out of Scope)**:
   - Single-job and localized test failures are auto-remediated; multi-service distributed race conditions require distributed tracing and are outside single-pipeline scope.
2. **Database Migrations with Data Loss Risk (Human Approval Mandate)**:
   - Changes touching `migrations/**` or `.sql` files get the `require_human_approval` policy decision, which is shown in the report. CIDRA never merges anything, so every fix already waits for a person; the decision does not change what is published.
3. **Flaky tests are reported, not quarantined**:
   - A flaky test is detected by running the tests 5 times, and only when the diagnosis already says `flaky_test` (G-16). CIDRA then reports it and attempts no fix. It does not quarantine, skip or mark the test.
4. **Static AST Analysis Boundaries (Dual-Gate Defense)**:
   - Static AST parsing reliably detects structural patterns (assertions, imports, skip decorators, system calls).
   - Highly obfuscated runtime dynamic metaprogramming (e.g. nested string decoders) is contained by the Docker sandbox runner: no network outside the install step, non-root user, `no-new-privileges`, memory, CPU and PID caps. The root filesystem is NOT read-only and capabilities are not dropped (`runner._create`).
5. **Air-Gapped LLM Inference Latency (Hardware Bound)**:
   - Local LLMs (Ollama / vLLM) behind an OpenAI-compatible URL keep prompts off external networks. No local model has been measured; turnaround depends on the hardware.
