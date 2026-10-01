# Architecture — CIDRA (Continuous Integration Debugging and Repair Agent)

> This is the contract layer. [2_scope_and_decisions.md](2_scope_and_decisions.md) says *what*
> CIDRA does and doesn't do; this says *how the pieces are shaped*. Phase 0 builds the graph
> skeleton against this schema, and every later phase fills in nodes. If you can redraw §4
> from memory and explain who writes each field in §3, you understand the system.

**Contents**
1. [System context](#1-system-context)
2. [Trust boundaries](#2-trust-boundaries)
3. [`DebugState` — the state object](#3-debugstate--the-state-object)
4. [The LangGraph topology](#4-the-langgraph-topology)
5. [Node-by-node contracts](#5-node-by-node-contracts)
6. [Routing logic](#6-routing-logic)
7. [The sandbox subsystem](#7-the-sandbox-subsystem)
8. [Sequence walkthroughs](#8-sequence-walkthroughs)
9. [Module layout](#9-module-layout)
10. [Idempotency & concurrency](#10-idempotency--concurrency)
11. [Failure modes & known weaknesses](#11-failure-modes--known-weaknesses)

---

## 1. System context

```mermaid
graph LR
    subgraph external["External systems"]
        GH["GitHub<br/>(CI, Repo, Comments)"]
        LLM["LLM provider (BYOK)<br/>any OpenAI-compatible API"]
    end

    subgraph cidra["CIDRA"]
        WH["Webhook Server<br/>FastAPI"]
        Q["Idempotency store<br/>SQLite"]
        AG["Agent<br/>LangGraph state machine"]
        SB["Sandbox Runner<br/>Docker SDK"]
    end

    subgraph host["Host machine"]
        DK["Docker daemon"]
        CT["Ephemeral containers<br/>network-off, capped"]
    end

    GH -- "1 . workflow_run: failure<br/>(HMAC-signed)" --> WH
    WH -- "2 . claim (run_id, sha)" --> Q
    WH -- "3 . dispatch<br/>(BackgroundTask)" --> AG
    AG -- "4 . fetch logs / repo" --> GH
    AG -- "5 . analyse + generate fix" --> LLM
    AG -- "6 . reproduce / verify" --> SB
    SB --> DK --> CT
    AG -- "7 . post comment" --> GH

    style cidra fill:#eef6ff,stroke:#4a7ab5
    style host fill:#fff4e6,stroke:#c98a2e
    style external fill:#f3f0ff,stroke:#7a5ec4
```

Seven steps, three subsystems. The agent is the only component that talks to all three
external surfaces; everything else has exactly one job.

There is no job queue: the webhook handler claims the idempotency key, returns 200, and runs
the graph in a FastAPI `BackgroundTask` in the same process (`server/worker.py`). The same
graph is also invoked directly by `cidra action` (the composite GitHub Action) and
`cidra fix` (local, dry-run), which skip the webhook entirely.

### 1.1 LLM access is BYOK

CIDRA ships no model credentials and is not tied to one vendor. The operator brings their own
key for any OpenAI-compatible endpoint:

| Setting | Purpose |
|---|---|
| `CIDRA_API_KEY` + `CIDRA_BASE_URL` | Primary provider (required) |
| `CIDRA_MODEL_ANALYZE` / `CIDRA_MODEL_FIX` | Model ids for the two LLM nodes |
| `OPENROUTER_API_KEY[_2]`, `GROQ_API_KEY`, `NVIDIA_API_KEY_KIMI` / `_GLM` | Optional fallback providers, tried in order when the primary fails |

All calls go through `integrations/llm.py::structured()`: one forced tool call, Pydantic-
validated, 3 tries per provider (65s backoff on a 429) before falling through to the next.
Keys live in the host process environment only; the sandbox is created with a fixed
environment and no host env passthrough, so repo code and LLM patches never see them.

The primary call sends the configured model id (`CIDRA_MODEL_ANALYZE` / `CIDRA_MODEL_FIX`);
each fallback provider uses its own fixed model id, since ids are provider-specific.

---

## 2. Trust boundaries

The single most important structural idea in CIDRA. Three zones, and code moves between them
under strict rules.

```mermaid
graph TB
    subgraph z1["ZONE 1 — Untrusted input"]
        direction LR
        P["Webhook payload<br/>from public internet"]
    end

    subgraph z2["ZONE 2 — Trusted orchestration (host process)"]
        direction LR
        G["LangGraph nodes"]
        L["LLM responses<br/>(untrusted DATA)"]
    end

    subgraph z3["ZONE 3 — Hostile execution (container)"]
        direction LR
        R["Repo test suite"]
        F["LLM-proposed patch"]
    end

    P -->|"HMAC verify<br/>reject if invalid"| G
    G -->|"prompt"| L
    L -->|"Pydantic validate<br/>never eval, never shell"| G
    G -->|"patch as data<br/>+ fixed command"| R
    G --> F
    F -.->|"CANNOT escape:<br/>no network, no socket,<br/>capped, timed out"| z2

    style z1 fill:#ffe6e6,stroke:#c0392b
    style z2 fill:#e8f5e9,stroke:#2e7d32
    style z3 fill:#fff3e0,stroke:#e65100
```

| Zone | Contains | Enforcement |
|---|---|---|
| 1 — Untrusted | Webhook payloads | HMAC-SHA256 verification before parsing anything |
| 2 — Trusted | Graph, routers, state | Never `eval`/`exec`/shell-interpolates LLM output |
| 3 — Hostile | Repo code, LLM patches | Runs only in a container: no network, no docker socket, resource-capped, hard timeout |

**The rule that matters:** the LLM's output is untrusted *even though we wrote the prompt*.
It crosses into Zone 3 as **data** — a unified diff to apply, never a command string the host
builds a shell call from. See §7 for how the API shape enforces this.

---

## 3. `DebugState` — the state object

Every node is `state in → partial state out`. No node reaches outside this object for input,
and no node writes a field it doesn't own.

```python
from typing import TypedDict, Literal, Optional
from pydantic import BaseModel, Field

FailureCategory = Literal[
    "missing_dependency",    # rank 1
    "assertion_error",       # rank 2
    "env_config_error",      # rank 3
    "flaky_test",            # rank 4 — structurally distinct path, see §4.3
    "unknown",               # out of scope or analysis failed
]

Outcome = Literal[
    "verified_fix",     # patch proven green in sandbox
    "flaky_detected",   # non-determinism confirmed; no patch attempted
    "diagnosis_only",   # root cause identified, fix not achieved
    "failed",           # could not reproduce or could not diagnose
]

class Analysis(BaseModel):
    """LLM output. Pydantic-validated. `category` is what routes the graph."""
    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str                          # verbatim log lines supporting the call
    proposed_action: str                   # human-readable intent, NOT code
    file: Optional[str] = None
    line: Optional[int] = None
    failing_test: Optional[str] = None     # "tests/test_api.py::test_auth"
    missing_package: Optional[str] = None  # rank-1 only
    env_var: Optional[str] = None          # rank-3 only

class SandboxResult(BaseModel):
    """One container execution. Immutable record."""
    step: Literal["checkout", "install", "test", "verify"]
    exit_code: int
    stdout_tail: str          # TRUNCATED — full output never enters state
    stderr_tail: str
    duration_s: float
    timed_out: bool
    passed: bool

class DebugState(TypedDict, total=False):
    # ---- Identity — written by entrypoint, read by everything ----
    run_id: str                   # idempotency key
    repo: str                     # "owner/name"
    commit_sha: str
    workflow_file: Optional[str]

    # ---- Ingestion — written by fetch_log / isolate_error ----
    raw_log: str                  # NEVER sent to the LLM
    error_region: str             # ~50-200 lines; the LLM's actual input
    log_markers: list[str]        # which anchors matched (debuggability)

    # ---- Analysis — written by analyze / validate_analysis ----
    analysis: Optional[Analysis]
    analysis_attempts: int        # bounded: MAX_ANALYSIS_ATTEMPTS = 2
    analysis_error: Optional[str] # last validation failure, fed back on retry

    # ---- Environment — written by prepare_sandbox ----
    image_tag: Optional[str]      # base image used
    env_ready: bool

    # ---- Reproduction — written by reproduce_once / reproduce_n_times ----
    reproduced: bool
    repro_results: list[SandboxResult]
    flaky_pass_count: Optional[int]   # flaky path only: passes out of N

    # ---- Fix + verify — written by generate_fix / apply_patch / verify_fix ----
    fix_diff: Optional[str]
    fix_attempts: int             # bounded: MAX_FIX_ATTEMPTS = 3
    patch_applied: bool
    verified: bool                # HARD INVARIANT — see below
    verify_results: list[SandboxResult]

    # ---- Terminal — written by compose_report / publish ----
    outcome: Outcome
    final_output: str
    comment_url: Optional[str]
```

### 3.1 Field ownership

Exactly one writer per field. This is what keeps agent state from becoming a mess.

| Field group | Sole writer | Readers |
|---|---|---|
| `run_id`, `repo`, `commit_sha` | entrypoint | all nodes |
| `raw_log` | `fetch_log` | `isolate_error` only |
| `error_region`, `log_markers` | `isolate_error` | `analyze`, `compose_report` |
| `analysis`, `analysis_attempts` | `analyze` / `validate_analysis` | routers, fix nodes, report |
| `reproduced`, `repro_results` | `reproduce_once` / `reproduce_n_times` | routers, report |
| `fix_diff`, `fix_attempts` | `generate_fix` | `apply_patch`, `verify_fix`, report |
| **`verified`** | **`verify_fix` only** | `route_after_verify`, `compose_report` |
| `outcome`, `final_output` | `compose_report` | `publish` |

> **Why `verified` has exactly one writer:** it is the field the entire pitch rests on
> (scope doc §7 — *zero false "fixed" claims*). Only the node that actually observed a green
> container run can set it. This is a structural guarantee, not a code-review convention.

---

## 4. The LangGraph topology

### 4.1 Full graph

```mermaid
stateDiagram-v2
    direction TB
    [*] --> fetch_log

    state "INGESTION" as ING {
        fetch_log --> isolate_error
    }

    state "ANALYSIS" as ANA {
        isolate_error --> analyze
        analyze --> validate_analysis
    }

    state ck_valid <<choice>>
    validate_analysis --> ck_valid
    ck_valid --> analyze: invalid JSON<br/>attempts &lt; 2
    ck_valid --> compose_report: invalid JSON<br/>attempts ≥ 2 → failed
    ck_valid --> checkout_commit: valid

    state "ENVIRONMENT" as ENV {
        checkout_commit --> prepare_sandbox
        prepare_sandbox --> install_deps
    }

    state ck_env <<choice>>
    install_deps --> ck_env
    ck_env --> compose_report: env broken → failed
    ck_env --> route_category: ready

    state ck_cat <<choice>>
    route_category --> ck_cat
    ck_cat --> reproduce_n_times: category ==<br/>flaky_test
    ck_cat --> reproduce_once: all other<br/>categories

    state "FLAKY PATH" as FLK {
        reproduce_n_times --> classify_flakiness
    }

    state ck_flaky <<choice>>
    classify_flakiness --> ck_flaky
    ck_flaky --> compose_report: intermittent →<br/>flaky_detected
    ck_flaky --> reproduce_once: consistently red<br/>(misclassified)

    state ck_repro <<choice>>
    reproduce_once --> ck_repro
    ck_repro --> compose_report: not reproduced<br/>→ failed
    ck_repro --> localize: reproduced red
    localize --> select_strategy

    state ck_strat <<choice>>
    select_strategy --> ck_strat
    ck_strat --> compose_report: no strategy →<br/>diagnosis_only
    ck_strat --> audit_patch: fix-cache hit<br/>(skip LLM)
    ck_strat --> generate_fix: otherwise

    state "FIX + VERIFY" as FIX {
        generate_fix --> audit_patch
        apply_patch --> verify_fix
    }

    state ck_audit <<choice>>
    audit_patch --> ck_audit
    ck_audit --> apply_patch: audit ok
    ck_audit --> compose_report: rejected →<br/>diagnosis_only

    state ck_verify <<choice>>
    verify_fix --> ck_verify
    ck_verify --> generate_fix: red, attempts &lt; 3<br/>(feed error back)
    ck_verify --> compose_report: red, attempts ≥ 3<br/>→ diagnosis_only
    ck_verify --> compose_report: GREEN →<br/>verified_fix

    state "OUTPUT" as OUT {
        compose_report --> publish
        publish --> cleanup
    }

    cleanup --> [*]
```

### 4.2 Why this many nodes

The temptation is to collapse this into six fat nodes. Don't — each split below exists for
a reason:

| Split | Why it's separate |
|---|---|
| `fetch_log` / `isolate_error` | Isolation must be **pure** so Phase 2 can regression-test it against fixtures with zero mocking |
| `analyze` / `validate_analysis` | Retry-on-malformed-JSON needs its own edge; folding it in means a hidden loop inside a node |
| `checkout_commit` / `prepare_sandbox` / `install_deps` | Three different failure modes with three different messages. Checkout runs **first**: it makes a per-run clone through the hardened git wrapper and strips `.git`, and the sandbox is then created from that tree. Also: `install_deps` is the **only** step allowed network access (§7) |
| `localize` | SBFL (coverage spectrum ranking) runs only on a confirmed-red repro and is best-effort; keeping it out of `generate_fix` means a missing `coverage` package degrades the prompt, not the run |
| `generate_fix` / `audit_patch` | The audit is a static, no-LLM gate (weakened tests, forbidden paths, size ceiling, `cidra.policy.yml`). As its own node, a rejected diff has its own edge to the report and never reaches the sandbox. Cached diffs pass through it too |
| `reproduce_once` / `reproduce_n_times` | Fundamentally different semantics — one expects red, the other expects *inconsistency* (§4.3) |
| `select_strategy` / `generate_fix` | Strategy selection is deterministic per-category routing; generation is an LLM call. Keeping them apart means you can unit-test routing without burning tokens |
| `generate_fix` / `apply_patch` / `verify_fix` | A patch can fail to *apply* (malformed diff) — that's a different failure than a patch that applies but doesn't fix. Separate nodes, separate error messages |
| `compose_report` / `publish` | Report composition is pure and testable; publishing does network I/O. Also lets you dry-run the full graph with publishing disabled |
| `cleanup` | Runs on **every** terminal path. Containers/volumes must never leak |

### 4.3 The flaky-test path — why it's structurally different

This is the design decision that must exist in the architecture, not be discovered mid-build.
Scope doc §2 ranks flaky last precisely because it does not fit the `fix → verify` shape.

```mermaid
graph TB
    A["reproduce_n_times<br/>N = 5 identical runs"] --> B{"classify_flakiness<br/>count passes"}
    B -->|"0 &lt; passes &lt; N<br/>NON-DETERMINISTIC"| C["outcome = flaky_detected<br/>report + quarantine suggestion<br/><b>no patch generated</b>"]
    B -->|"passes == 0<br/>consistently RED"| D["LLM misclassified<br/>re-route, exclude flaky_test<br/>(bounded: once)"]
    B -->|"passes == N<br/>consistently GREEN"| E["cannot reproduce<br/>outcome = failed"]

    style C fill:#fff3e0,stroke:#e65100
    style D fill:#ffe6e6,stroke:#c0392b
    style E fill:#eceff1,stroke:#546e7a
```

| Dimension | Ranks 1-3 (dependency / assertion / config) | Rank 4 (flaky) |
|---|---|---|
| Reproduction | 1 run, expect **consistently red** | **N=5 runs**, expect **inconsistency** |
| Fix generation | Yes — LLM produces a unified diff | **None.** There is no code fix to make |
| Success signal | Sandbox turns **green** after patch | Non-determinism **confirmed** across runs |
| Terminal outcome | `verified_fix` | `flaky_detected` |

```python
def classify_flakiness(state: DebugState) -> dict:
    results = state["repro_results"]
    passes = sum(r.passed for r in results)
    n = len(results)
    if 0 < passes < n:
        return {"flaky_pass_count": passes, "outcome": "flaky_detected"}
    if passes == n:
        return {"flaky_pass_count": passes, "reproduced": False}   # → failed
    return {"flaky_pass_count": 0, "reproduced": True}             # misclassified → rank 1-3
```

> This is the differentiator named in scope doc §0. OpenHands' own material concedes that
> non-determinism breaks its pass/fail feedback loop. CIDRA's answer is that flakiness gets a
> **first-class terminal outcome** rather than being forced through a fix-verify cycle that
> cannot produce a meaningful signal.

### 4.4 Bounded loops

Three loops exist. All are bounded, and the constants live in one config module — these are
the numbers an interviewer will ask about.

```mermaid
graph LR
    subgraph L1["Loop 1 — analysis retry"]
        A1["analyze"] --> A2["validate"] -->|"invalid"| A1
    end
    subgraph L2["Loop 2 — fix retry"]
        B1["generate_fix"] --> B2["verify"] -->|"still red"| B1
    end
    subgraph L3["Loop 3 — flaky sampling"]
        C1["reproduce_n_times<br/>fixed N, not a retry loop"]
    end

    L1 -.->|"MAX_ANALYSIS_ATTEMPTS = 2"| X[" "]
    L2 -.->|"MAX_FIX_ATTEMPTS = 3"| X
    L3 -.->|"FLAKY_RUNS = 5"| X
    style X fill:none,stroke:none
```

Loop 3 is not a retry loop — it is a fixed-N sample. Worth stating because it's the one that
looks unbounded at a glance.

---

## 5. Node-by-node contracts

Build checklist for Phases 2-7. "Pure" means no I/O — trivially testable against fixtures.

| # | Node | Reads | Writes | I/O | Pure | Phase |
|---|---|---|---|---|---|---|
| 1 | `fetch_log` | `run_id`, `repo` | `raw_log` | GitHub | ✗ | 2 |
| 2 | `isolate_error` | `raw_log` | `error_region`, `log_markers` | — | ✓ | 2 |
| 3 | `analyze` | `error_region`, `analysis_error` | `analysis`(raw), `analysis_attempts` | LLM (BYOK) | ✗ | 3 |
| 4 | `validate_analysis` | raw LLM output | `analysis`, `analysis_error` | — | ✓ | 3 |
| 5 | `checkout_commit` (runs before 6) | `commit_sha`, `source_dir` | `source_dir` | host git | ✗ | 9 |
| 6 | `prepare_sandbox` | `source_dir` | `image_tag`, `env_ready` on failure | Docker | ✗ | 4 |
| 7 | `install_deps` | — | `env_ready`, `repro_results[+]` | Docker **+net** | ✗ | 4 |
| 8 | `route_category` | `analysis.category` | — (router) | — | ✓ | 4 |
| 9 | `reproduce_once` | `analysis.failing_test` | `reproduced`, `repro_results[+]` | Docker | ✗ | 4 |
| 10 | `reproduce_n_times` | `analysis.failing_test` | `repro_results[×N]` | Docker ×N | ✗ | 5 |
| 11 | `classify_flakiness` | `repro_results` | `flaky_pass_count`, `outcome` | — | ✓ | 5 |
| 11b | `localize` | — | `sbfl_ranking`, `sbfl_evidence` | Docker | ✗ | 8 |
| 12 | `select_strategy` | `analysis.category`, `error_region` | `fix_strategy`, `fingerprint`, cached `fix_diff` | fix-cache file | ✗ | 5/11 |
| 13 | `generate_fix` | `analysis`, `error_region`, `sbfl_evidence`, last `verify_results` | `fix_diff`, `fix_attempts` | LLM (BYOK) | ✗ | 5 |
| 13b | `audit_patch` | `fix_diff` | `patch_audit_ok`, `patch_audit_reasons`, `requires_human_approval` | policy file | ✗ | 10 |
| 14 | `apply_patch` | `fix_diff` | `patch_applied` | Docker | ✗ | 5 |
| 15 | `verify_fix` | — | **`verified`**, `verify_results` | Docker | ✗ | 5 |
| 16 | `compose_report` | everything | `outcome`, `final_output` | — | ✓ | 6 |
| 17 | `publish` | `final_output` | `comment_url` | GitHub | ✗ | 6 |
| 18 | `cleanup` | — | — | Docker | ✗ | 4 |

Twenty nodes. The pure ones are your cheap, fast, deterministic test surface — build them
first in each phase. (`select_strategy` stopped being pure when the fix cache arrived, and
`compose_report` now loads the policy file to build the audit manifest.)

### 5.1 Fix strategies (node 12 → 13)

`select_strategy` is deterministic dispatch; only `generate_fix` calls the LLM.

```mermaid
graph LR
    S{"select_strategy<br/>on analysis.category"}
    S -->|missing_dependency| D["append to requirements.txt<br/><i>template-driven, LLM optional</i>"]
    S -->|assertion_error| A["patch assertion/fixture<br/><i>LLM-generated diff</i>"]
    S -->|env_config_error| U2["no strategy (for now)<br/>→ diagnosis_only"]
    S -->|unknown| U["no strategy<br/>→ diagnosis_only"]

    style D fill:#e8f5e9,stroke:#2e7d32
    style U fill:#eceff1,stroke:#546e7a
    style U2 fill:#eceff1,stroke:#546e7a
```

Note `missing_dependency` (rank 1) is nearly template-driven — `analysis.missing_package`
plus an append. That's *why* it's rank 1: highest reliability, least LLM dependence.

**Decision: `env_config_error` has no fix strategy yet (2026-08-22).** `patch_workflow`
would edit `.github/workflows/ci.yml`, but the sandbox never reads that file — it invokes
`pytest` directly, so a workflow edit is invisible to `verify_fix`. Applying the patch and
then "verifying" it in the sandbox would either fail a correct fix or pass one that was
never actually exercised. Both violate the one rule that matters most: never claim a fix
that wasn't verified.

So `env_config_error` is intentionally absent from `STRATEGIES` in `cidra/nodes/fix.py`.
`select_strategy` returns `fix_strategy: None`, and `route_after_strategy` sends it straight
to `compose_report` — same path as `unknown` — for `outcome: diagnosis_only` with zero LLM
calls. This is correct behavior for a fixture like F-03 (env-config break), not a stub: it's
the honest answer given what the sandbox can actually verify today.

**Reintroduce it (Option C) when workflow fixes need to go further than diagnosis** — e.g.
opening a PR in Phase 6/7. That requires the sandbox to parse `ci.yml`'s `env:` block and
inject those vars before running the test, so the sandbox run fails without the fix and
passes with it — i.e., *real* verification of a workflow-level change, not sandbox theater.

---

## 6. Routing logic

Every conditional edge is a small pure function. No LLM calls, no I/O — just reads of state.

```python
def route_after_validate(state) -> str:
    if state.get("policy_decision") == "strict_refusal":
        return "compose_report"
    if state.get("analysis") is not None:
        return "checkout_commit"
    return "analyze" if state["analysis_attempts"] < MAX_ANALYSIS_ATTEMPTS else "compose_report"

def route_after_env(state) -> str:
    return "route_category" if state["env_ready"] else "compose_report"

def route_category(state) -> str:
    return ("reproduce_n_times"
            if state["analysis"].category == "flaky_test"
            else "reproduce_once")

def route_after_flaky(state) -> str:
    if state.get("outcome") == "flaky_detected":
        return "compose_report"
    return "reproduce_once" if state["reproduced"] else "compose_report"

def route_after_reproduce(state) -> str:
    return "localize" if state["reproduced"] else "compose_report"

def route_after_strategy(state) -> str:
    if not state.get("fix_strategy"):
        return "compose_report"
    if state.get("cache_hit") and state.get("fix_diff"):
        return "audit_patch"          # cached diff skips the LLM, never the audit or verify
    return "generate_fix"

def route_after_audit(state) -> str:
    return "apply_patch" if state.get("patch_audit_ok") else "compose_report"

def route_after_verify(state) -> str:
    if state["verified"]:
        return "compose_report"
    return "generate_fix" if state["fix_attempts"] < MAX_FIX_ATTEMPTS else "compose_report"
```

All eight fit on one screen and are unit-testable with a dict — no mocking, no tokens.

---

## 7. The sandbox subsystem

The graph never touches Docker directly. One module owns it, so hardening lives in exactly
one place (scope doc §6 rules are enforced here or nowhere).

```mermaid
graph TB
    subgraph host["Host process (Zone 2)"]
        N["Graph nodes<br/>6, 7, 9, 10, 14, 15"]
        R["sandbox/runner.py<br/><b>only Docker caller</b>"]
    end

    subgraph daemon["Docker daemon"]
        I["cidra-base:py311<br/>prebuilt toolchain"]
        C["ephemeral container"]
    end

    N -->|"run_in_sandbox(...)"| R
    R -->|"create from image"| I
    I --> C
    C -->|"SandboxResult"| R
    R -->|"try/finally: remove"| C

    C -.->|"network_mode=none<br/>(except install_deps)"| X1["✗ internet"]
    C -.->|"no socket mount"| X2["✗ docker.sock"]
    C -.->|"mem/cpu/pids capped"| X3["✗ fork bomb"]
    C -.->|"hard timeout"| X4["✗ hang"]

    style X1 fill:#ffe6e6,stroke:#c0392b
    style X2 fill:#ffe6e6,stroke:#c0392b
    style X3 fill:#ffe6e6,stroke:#c0392b
    style X4 fill:#ffe6e6,stroke:#c0392b
```

```python
def run_in_sandbox(
    step: Literal["checkout", "install", "test", "verify"],
    repo: str,
    commit_sha: str,
    command: str,                     # fixed, from our code — never LLM-authored
    patch: Optional[str] = None,      # unified diff, applied post-checkout
    network: bool = False,            # True ONLY for step == "install"
    timeout_s: int = DEFAULT_TIMEOUT,
) -> SandboxResult:
    """
    Contract:
      - container created, used, destroyed within this call (try/finally)
      - network_mode="none" unless network=True
      - mem_limit / cpu_quota / pids_limit ALWAYS set
      - never --privileged; never mounts /var/run/docker.sock
      - returns a SandboxResult even on timeout/crash; raises only on infra failure
    """
```

**The API shape is itself a safety control.** There is no `privileged` parameter to pass and
no way to opt out of the caps — a caller cannot weaken isolation without editing this module.
`command` is always constructed by CIDRA's own code; the LLM only ever supplies `patch`, which
is data. Full flags, base-image contents, and the adversarial test set → `6_sandbox_spec.md`.

---

## 8. Sequence walkthroughs

### 8.1 Happy path — missing dependency (rank 1)

```mermaid
sequenceDiagram
    autonumber
    participant GH as GitHub
    participant WH as Webhook
    participant AG as Agent (graph)
    participant AI as LLM (BYOK)
    participant SB as Sandbox

    GH->>WH: workflow_run.failure (HMAC)
    WH->>WH: verify sig, claim (run_id, sha)
    WH-->>GH: 200 OK (immediate)
    WH->>AG: BackgroundTask: process_job

    AG->>GH: fetch_log
    GH-->>AG: 12k lines
    AG->>AG: isolate_error → 80 lines
    AG->>AI: analyze(error_region)
    AI-->>AG: {category: missing_dependency,<br/>missing_package: "requests", conf: 0.95}
    AG->>AG: validate_analysis ✓

    AG->>AG: checkout_commit (host git, .git stripped)
    AG->>SB: prepare + install (net ON for install only)
    SB-->>AG: env_ready
    AG->>SB: reproduce_once
    SB-->>AG: RED ✓ (ModuleNotFoundError)
    AG->>SB: localize (SBFL, best-effort)

    AG->>AG: select_strategy → dependency (cache miss)
    AG->>AI: generate_fix
    AI-->>AG: diff: +requests to requirements.txt
    AG->>AG: audit_patch ✓
    AG->>SB: apply_patch + verify_fix
    SB-->>AG: GREEN ✓
    AG->>AG: verified = True

    AG->>AG: compose_report → verified_fix
    AG->>GH: publish comment
    AG->>SB: cleanup
```

### 8.2 Flaky path (rank 4)

```mermaid
sequenceDiagram
    autonumber
    participant AG as Agent (graph)
    participant AI as LLM (BYOK)
    participant SB as Sandbox

    AG->>AI: analyze(error_region)
    AI-->>AG: {category: flaky_test, conf: 0.7}
    AG->>AG: route_category → FLAKY branch

    loop N = 5 identical runs
        AG->>SB: reproduce (same commit, same test)
        SB-->>AG: pass / fail
    end

    AG->>AG: classify_flakiness → 3 fail, 2 pass
    Note over AG: 0 &lt; passes &lt; N ⇒ non-deterministic
    AG->>AG: outcome = flaky_detected<br/><b>no fix generated</b>
    AG->>AG: compose_report (flakiness + quarantine advice)
```

### 8.3 Degraded path — fix never goes green

```mermaid
sequenceDiagram
    autonumber
    participant AG as Agent (graph)
    participant AI as LLM (BYOK)
    participant SB as Sandbox

    AG->>SB: reproduce_once
    SB-->>AG: RED ✓

    loop attempts 1 . . 3
        AG->>AI: generate_fix (with previous error fed back)
        AI-->>AG: candidate diff
        AG->>SB: apply_patch + verify_fix
        SB-->>AG: still RED
    end

    Note over AG: fix_attempts == MAX_FIX_ATTEMPTS<br/>verified stays False
    AG->>AG: outcome = diagnosis_only
    Note over AG: Reports root cause + attempts.<br/><b>Never claims a fix.</b>
```

That last note is the §7 invariant made visible: an unverified patch is reported as a
suggestion under `diagnosis_only`, never as a fix.

---

## 9. Module layout

```
cidra/
├── config.py                 # ALL bounds/limits/constants in one place
├── state.py                  # DebugState, Analysis, SandboxResult, Outcome
├── graph.py                  # graph assembly: nodes + edges + routers
├── routers.py                # the pure routing functions (§6)
├── cli.py                    # `cidra action | fix | dashboard` entrypoints
├── git_ops.py                # hardened git wrapper (hooks off, argv only)
├── policy.py                 # cidra.policy.yml engine
├── audit_manifest.py         # signed per-run audit manifest
├── history.py                # run history + dashboard telemetry
├── nodes/
│   ├── ingest.py             # fetch_log, isolate_error              (Ph 2)
│   ├── analyze.py            # analyze, validate_analysis            (Ph 3)
│   ├── environment.py        # checkout, prepare_sandbox, install    (Ph 4/9)
│   ├── checkout.py           # per-run isolated clone, .git stripped (Ph 9)
│   ├── reproduce.py          # reproduce_once, reproduce_n_times,
│   │                         # classify_flakiness                    (Ph 4/5)
│   ├── localize.py, sbfl.py  # SBFL fault localization               (Ph 8)
│   ├── fix.py                # select_strategy, generate_fix,
│   │                         # apply_patch, verify_fix               (Ph 5)
│   ├── fingerprint.py, fix_cache.py  # verified-fix cache            (Ph 11)
│   ├── audit.py              # audit_patch static gate               (Ph 10)
│   ├── pr.py                 # fix branch for the draft PR           (Ph 9)
│   └── publish.py, report.py # compose_report, publish, cleanup      (Ph 6)
├── sandbox/
│   ├── runner.py             # Session / run_in_sandbox — ONLY Docker caller
│   ├── limits.py             # mem/cpu/pids/timeout constants
│   └── Dockerfile            # prebuilt toolchain image
├── integrations/
│   ├── llm.py                # BYOK OpenAI-compatible client + fallback chain
│   ├── github.py             # read-only: logs, run metadata
│   └── github_write.py       # write token: comment, draft PR
├── server/
│   ├── app.py                # FastAPI webhook + dashboard API       (Ph 7)
│   ├── security.py           # HMAC verification
│   ├── events.py             # payload filter → WebhookJob
│   ├── idempotency.py        # SQLite claim store
│   ├── worker.py             # background dispatch of the graph
│   └── settings.py           # dashboard settings API
├── prompts/                  # versioned templates (→ 7_prompts.md)
└── eval/
    ├── fixtures/             # saved logs + expected JSON            (Ph 1)
    ├── adversarial/          # sandbox escape attempts               (Ph 4/6)
    └── run_eval.py           # regenerates the eval table (scope §7)
```

`eval/` sits alongside source rather than inside `tests/` deliberately — per scope doc §7 the
eval table is a **primary deliverable**, not test scaffolding. It re-runs after every prompt
or logic change.

---

## 10. Idempotency & concurrency

Webhook retries are guaranteed, so this is not optional.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> claimed: webhook, HMAC ok,<br/>INSERT wins
    claimed --> claimed: duplicate delivery → 200 no-op
    claimed --> [*]: graph runs once in background
```

- **Key on `(run_id, commit_sha)`.** `IdempotencyStore.claim()` is one SQLite `INSERT`
  against a primary key, so exactly one delivery wins. Already present → 200, do nothing.
- **One job per key.** Two containers racing the same commit wastes resources and can
  produce contradictory `verified` values.
- Handler does the minimum before 200: verify HMAC → parse + filter → claim → schedule the
  `BackgroundTask`.
- **Crash recovery.** If the graph raises, the worker releases the claim, so redelivering
  the webhook (GitHub UI or `scripts/replay_delivery.py`) re-drives the run. GitHub does not
  redeliver on its own, because the handler already returned 200.
- **Not implemented: transition tracking.** The store records only the claim, not
  `running` / `done`, and has no TTL. A process killed mid-run leaves its claim behind.
  Sessions are also held in an in-process dict, so this design assumes a single server
  process.

---

## 11. Failure modes & known weaknesses

Stated deliberately so they're design decisions, not surprises. These belong in the README —
naming them is stronger than pretending they don't exist.

| # | Weakness | Mitigation / stance |
|---|---|---|
| 1 | `analysis.failing_test` missing or wrong → `reproduce_once` doesn't know what to run | Fall back to running the whole suite. Slower, still correct |
| 2 | **Green-but-wrong fix** — LLM edits the assertion to match buggy behaviour | Verification proves *the build goes green*, not *the code is correct*. Stated plainly in README |
| 3 | `install_deps` requires network — a real hole in isolation | Scoped to that single step; every other step is `network_mode=none`. Documented, not hidden |
| 4 | Flaky detection at N=5 is statistical, not proof — a 1-in-50 flake reads as passing | Report the sensitivity limit alongside the finding |
| 5 | LLM misclassifies a hard failure as flaky | `classify_flakiness` catches `passes == 0` and re-routes once (§4.3) |
| 6 | Malformed diff from LLM fails to apply | `apply_patch` is its own node with its own error path; counts against `fix_attempts` |
| 7 | Container leak on crash | `cleanup` runs on every terminal path; `run_in_sandbox` uses try/finally independently |

---

## 12. Open items → next docs

| Doc | Contents | Phase |
|---|---|---|
| `5_fixtures.md` | Practice repo, broken commits, saved logs, expected JSON | 1 |
| `6_sandbox_spec.md` | Exact flags, base image, adversarial test set | 4 |
| `7_prompts.md` | Prompt text, schema, few-shots, version log | 3 |
| `8_api_contracts.md` | Webhook payload, HMAC steps, idempotency store | 7 |
