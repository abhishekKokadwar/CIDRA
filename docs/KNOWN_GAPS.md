# Known Gaps — CIDRA

> The honest list. Everything built-but-not-yet-fully-proven, or deliberately deferred,
> lives here so it is revisited rather than forgotten. Each gap says what's missing, why,
> what unblocks it, and how we'll know it's closed.
>
> **Blocker legend:** 🐳 needs a running Docker daemon · 🔑 needs LLM credits (OpenRouter)
> · 🌐 needs a write token / live GitHub · 🛠 real code work (not just an environment)
>
> Last reviewed: 2026-09-21.

---

## Open gaps

### G-01 · Live SBFL coverage collection (Phase 8) — 🐳
**What:** `cidra/nodes/localize.py` collects per-test coverage *inside the container* via a
pytest plugin, builds the spectrum, and feeds the SBFL ranking into the fix prompt. The
plugin parser, clean degradation (no coverage/pytest → no-evidence), and evidence injection
are unit-tested (`tests/unit/test_localize.py` 5/5). What is **not** yet run end-to-end is the
actual coverage collection in a live sandbox on a real fixture.
**Why open:** Docker was down when Phase 8 was built; the base image also lacks
coverage+pytest, so collection only fires after a repo installs them (best-effort by design).
**Unblock / fix:** bring Docker up, run a fixture that installs pytest, confirm
`CIDRA_SBFL_JSON=` is emitted and a non-empty `sbfl_evidence` reaches the fix context.
**Done when:** an integration test under `tests/integration/` drives `localize` on a real
session and asserts a non-empty ranking whose #1 is the known-buggy element.
**Note:** the SBFL *math* and *order-independence* (the phase's actual claim) are fully proven
offline — this gap is only the live plumbing.

### G-02 · Full engine live run via webhook (Phase 7) — 🐳 🔑 🌐
**What:** the webhook path is proven end-to-end *except* the final analysis→sandbox→comment
leg. A real replayed delivery got as far as fetching the CI log, then the LLM call returned
OpenRouter `402: insufficient credits` (correctly handled as `outcome=failed`).
**Unblock / fix:** add OpenRouter credits (or point `CIDRA_BASE_URL`/`CIDRA_API_KEY` at a
funded endpoint) + Docker up. Then
`python scripts/replay_delivery.py --repo helpmecode69/cidra-practice --run-id <RUN_ID>`.
**Done when:** a replayed real failure produces a verified fix and a posted comment, with no
manual command; `--twice` shows the idempotency no-op.

### G-03 · Draft-PR live POST (Phase 9.6) — 🔑 🌐
**What:** branch-from-diff + push + draft-PR REST are built and unit-tested against a mocked
GitHub API and a real local git remote (`tests/unit/test_pr.py` 7/7). The *live POST to
github.com* has not run.
**Unblock / fix:** same gate as G-02 (needs a verified fix, so LLM credits) + the write token.
**Done when:** a verified fix opens a real draft PR on `cidra-practice`; a re-run updates the
same PR (idempotent), never merges.

### G-04 · Live PR-thread comment (Phase 6 → 7) — 🔑 🌐
**What:** `publish` posts a real comment only when `issue_number` is present. The
practice-repo fixtures are branch pushes (`pull_requests=[]`), so publish dry-runs. The
comment composer + write path are unit-proven; a real posted comment on a PR has not run.
**Unblock / fix:** either open a PR for a fixture branch so SHA-lookup resolves it, or run
G-02 against a genuine PR. (Optional code: a commit-comment fallback for no-PR runs — see
G-08.)
**Done when:** a CIDRA comment appears on a real PR thread on `cidra-practice`.

### G-05 · Adversarial + benchmark on Docker are point-in-time (Phases 4/6/9) — 🐳
**What:** ADV-01..08 (8/8 contained) and the security benchmark (SEC-01/04/06/07 PASS) were
recorded on specific dates, not in CI. They must be re-run after any change to `runner.py`,
`limits.py`, `git_ops.py`, or `checkout.py` — currently a manual discipline.
**Unblock / fix:** a CI job (or a documented pre-merge step) that runs
`eval/adversarial/run_adversarial.py` and `eval/security_fixtures/run_benchmark.py` with
Docker up.
**Done when:** these run automatically and gate merges to the sandbox/git modules.

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

### G-14 · Web dashboard + live view + interactive HITL gate (Phase 13) — 🌐 🛠
The run-history store and the read-only Fleet TUI are built. Deferred: the React web
dashboard, the live container/token-spend view (needs a running run to observe), and the
interactive HITL approve/reject → PR gate (needs live GitHub). This is where the SR-20
decision trace becomes a clickable review surface (EU AI Act Art. 14).
**Done when:** a reviewer can see a run's trace + diff in a UI and approve/reject it, and the
live view shows in-flight container status.

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
