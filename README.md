<div align="center">

<p align="center">
  <img src="https://raw.githubusercontent.com/abhishekKokadwar/CIDRA/main/cidra/static/cidra_logo.png" alt="CIDRA Logo" width="440" />
</p>

**Continuous Integration Debugging and Repair Agent**

*The autonomous, deterministic CI repair agent powered by LangGraph, Spectrum-Based Fault Localization (SBFL), and a hardened, zero-trust Docker execution sandbox.*

[![PyPI version](https://img.shields.io/badge/pypi-v0.2.0-blue.svg)](https://pypi.org/project/cidra/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Security](https://img.shields.io/badge/sandbox-network--isolated-green.svg)](#7-hardened-sandbox--threat-model-adv-01adv-08)
[![CI](https://github.com/abhishekKokadwar/CIDRA/actions/workflows/test-cidra.yml/badge.svg)](https://github.com/abhishekKokadwar/CIDRA/actions/workflows/test-cidra.yml)
[![Dashboard](https://img.shields.io/badge/dashboard-react%20%2B%20vite-61dafb.svg)](#3-interactive-web-dashboard--hitl-gate)
[![Live Demo](https://img.shields.io/badge/live%20demo-cidra.vercel.app-2ea043.svg)](https://cidra.vercel.app)

<p align="center">
  <a href="#1-core-philosophy--the-triad-of-trust">Philosophy</a> •
  <a href="#2-langgraph-architecture--workflow">Architecture</a> •
  <a href="#3-interactive-web-dashboard--hitl-gate">Dashboard</a> •
  <a href="#4-quick-start--installation">Quick Start</a> •
  <a href="#5-github-actions-integration">CI Integration</a> •
  <a href="#6-multi-tier-llm-fallback-chain">LLM Fallback</a> •
  <a href="#7-hardened-sandbox--threat-model-adv-01adv-08">Threat Model</a> •
  <a href="#8-testing--verification-suite">Tests</a> •
  <a href="#9-repository-structure--development">Development</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/abhishekKokadwar/CIDRA/main/cidra/static/cidra-demo.svg" alt="CIDRA Terminal Execution Preview" width="820" />
</p>

---

</div>

## 1. Core Philosophy & The Triad of Trust

Most "AI repair" tools blindly guess fixes, hallucinate green test outcomes, and dump untested diffs directly into pull requests.

**CIDRA is built on an adversarial foundation**: it assumes LLMs will hallucinate, dependencies may carry supply-chain attacks, and tests can be non-deterministic. Every action is gated by the **Triad of Trust**:

```mermaid
flowchart TD
    subgraph Triad["THE TRIAD OF TRUST"]
        direction TB
        V["<b>VERIFY</b><br/>Red ➔ Patch ➔ Green<br/><i>Zero False Claims</i>"]
        D["<b>DECLARE</b><br/>Explicit Taxonomies<br/><i>0 Calls on Flaky Tests</i>"]
        C["<b>CONFINE</b><br/>Zero-Network Container<br/><i>AST Gate & Hardened Sandbox</i>"]
    end
    
    style Triad fill:#0d1117,stroke:#388bfd,stroke-width:2px,color:#58a6ff
    style V fill:#161b22,stroke:#2ea043,stroke-width:2px,color:#e6edf3
    style D fill:#161b22,stroke:#1f6feb,stroke-width:2px,color:#e6edf3
    style C fill:#161b22,stroke:#da3633,stroke-width:2px,color:#e6edf3
```

1. **Verify (Zero False Claims)**: CIDRA **never** claims a bug is fixed unless it reproduces the failure **red** inside an isolated Docker sandbox, applies the candidate patch, and re-executes the test suite to observe a clean **green** exit code. If a patch fails to apply or the tests remain red, the patch is discarded.
2. **Declare (Honest Failure Taxonomies)**: Rather than burning LLM tokens trying to fix environmental outages, flaky network calls, or invalid test configurations, CIDRA classifies root causes into formal categories. If an error is flaky, it declares `flaky_detected` and stops with **0 LLM fix attempts**.
3. **Confine (Zero-Trust Blast Radius)**: LLM generated code is treated as hostile by default. Patches pass through a static audit gate (blocking process execution, dynamic code evaluation, socket use, and edits that weaken or delete tests) before entering a network-disabled, non-root, PID-capped container.

---

## 2. LangGraph Architecture & Workflow

CIDRA orchestrates a 20-node cyclic state graph built on **LangGraph**. The workflow decouples log analysis from code generation and isolates untrusted operations into discrete state transitions.

### Runtime architecture

<p align="center">
  <img src="https://raw.githubusercontent.com/abhishekKokadwar/CIDRA/main/docs/assets/cidra-runtime-architecture.png" alt="CIDRA runtime architecture: GitHub webhook, repair engine, BYOK LLM gateway, patch audit gate, and the Docker sandbox across three trust zones" width="920" />
</p>

A signed `workflow_run` failure reaches the webhook receiver, which verifies the HMAC, claims an idempotency key, and runs the repair engine in the background. The engine calls your own LLM provider (**BYOK**: any OpenAI-compatible endpoint via `CIDRA_API_KEY` + `CIDRA_BASE_URL`), gates every diff through the patch audit, and executes repo code only inside network-off Docker containers. `cidra action` and `cidra fix` invoke the same engine without the webhook. Full detail: [docs/4_architecture.md](docs/4_architecture.md).

### Repair workflow

```mermaid
flowchart TD
    A(["CI Failure Webhook / CLI"]) --> B["ingest_log"]
    B --> C["fingerprint_error"]
    C --> D{"Fix in Cache?"}
    
    D -- "Yes (Cache Hit)" --> E["apply_cached_fix"]
    D -- "No (Cache Miss)" --> F["localize_fault_sbfl"]
    
    F --> G["reproduce_failure_red"]
    G --> H{"Flakiness Check (SR-08)"}
    
    H -- "Flaky (Intermittent)" --> I(["Terminal: flaky_detected"])
    H -- "Deterministic Red" --> J["analyze_root_cause"]
    
    J --> K["synthesize_patch"]
    K --> L{"AST Security Audit"}
    
    L -- "Violates Policy (ADV-07)" --> M["retry_patch_or_fail"]
    L -- "Clean AST" --> N["verify_patch_green"]
    
    N -- "Still Red (Failed)" --> O{"Attempt below Max Retries?"}
    O -- "Yes" --> K
    O -- "No" --> P(["Terminal: repair_exhausted"])
    
    N -- "Green (Verified)" --> Q["update_fix_cache"]
    Q --> R["publish_report"]
    R --> S["create_draft_pr / HITL"]
    S --> T(["Terminal: verified_fix"])
    
    style A fill:#161b22,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    style D fill:#161b22,stroke:#d29922,stroke-width:2px,color:#e6edf3
    style H fill:#161b22,stroke:#d29922,stroke-width:2px,color:#e6edf3
    style L fill:#161b22,stroke:#d29922,stroke-width:2px,color:#e6edf3
    style O fill:#161b22,stroke:#d29922,stroke-width:2px,color:#e6edf3
    style I fill:#21262d,stroke:#f85149,stroke-width:2px,color:#f85149
    style P fill:#21262d,stroke:#f85149,stroke-width:2px,color:#f85149
    style T fill:#21262d,stroke:#2ea043,stroke-width:2px,color:#3fb950
```

### Key Engineering Innovations

- **Spectrum-Based Fault Localization (SBFL)**: In [cidra/nodes/sbfl.py](cidra/nodes/sbfl.py), CIDRA computes **Ochiai** and **Tarantula** suspiciousness coefficients from execution spectra. It scores source code lines based on their ratio of execution in failing vs. passing test runs, ensuring the LLM fix prompt focuses exclusively on high-probability fault locations.
- **Statistical Flakiness Detection (SR-08)**: Non-deterministic tests break autonomous repair loops. CIDRA re-runs the suite 5 times in the sandbox. If an identical commit produces mixed pass/fail outcomes, the run is flagged as `flaky_detected` and halts immediately, preventing token waste on phantom bugs.
- **Static Patch Audit Gate**: Every patch is checked before it reaches the sandbox ([cidra/nodes/audit.py](cidra/nodes/audit.py)). The gate matches patterns on the added lines and uses Python's `ast` only to count assertions. It rejects `os.system`/`os.popen`, `subprocess`, `socket`, `eval`/`exec`, dynamic imports, unsafe deserialization, and any change that deletes, skips or weakens a test, or touches CI config. It does not block a plain `import os`; the no-network, non-root sandbox is what contains code the gate does not catch.
- **Persistent Fix Cache**: Hashes of error signatures and verified diffs are cached in `cidra_fix_cache.json`. Repeated CI breakages across different branches hit the cache for **instant, 0-token repairs**.

---

## 3. Interactive Web Dashboard & HITL Gate

CIDRA includes a reactive web dashboard built with React, Vite, and custom CSS design tokens. It provides real-time visibility into the repair pipeline and a **Human-In-The-Loop (HITL)** approval gate.

- **🌐 Live Cloud Dashboard (Mobile & Desktop)**: [https://cidra.vercel.app](https://cidra.vercel.app) *(accessible anywhere without installation)*
- **💻 Local Dashboard (CLI)**:
```bash
# Launch the dashboard locally (automatically opens in your browser)
cidra dashboard
```

```
┌────────────────────────────────────────────────────────────────────────┐
│  ⚡ CIDRA Command Center           [System: OPERATIONAL]  [● LIVE]     │
├────────────────────────────────────────────────────────────────────────┤
│  Total Interventions    Success Rate    Avg Time to Fix    Tokens Used │
│  42                     94.8%           38s                1.2M        │
├────────────────────────────────────────────────────────────────────────┤
│  Active Runs & Execution Timeline                                      │
│  [run-9821]  org/repo#142  missing_dependency   VERIFIED GREEN  [Diff] │
│  [run-9820]  org/repo#139  flaky_network        FLAKY DETECTED  [Logs] │
│  [run-9819]  org/repo#135  assertion_error      PENDING APPROVAL [HITL]│
└────────────────────────────────────────────────────────────────────────┘
```

### Dashboard Capabilities

1. **Command Center**: Real-time KPI counters tracking mean time to recovery (MTTR), repair success rate, token consumption, and system health status.
2. **Run Explorer**: Complete trace inspector displaying step-by-step state transitions, raw CI terminal logs, and syntax-highlighted unified diffs.
3. **Visual Orchestrator**: A diagram of the LangGraph topology with an animated walkthrough. It is illustrative and does not follow a live run.
4. **4-Tab Configuration Manager**:
   - **API Keys**: Configure OpenRouter, Groq, NVIDIA NIM, and GitHub PAT credentials with **one-click live round-trip latency probes**.
   - **Model Chain**: Configure analysis models, fix models, and base URLs.
   - **Flakiness & Sandbox**: Shows the flaky-run count, container timeouts and retry limits the engine is using. These are fixed in code and read-only here.
   - **Runtime Status**: View active paths, worktree directories, and SQLite database connectivity.
5. **HITL (Human-in-the-Loop) Review**: Inspect candidate diffs and the verification result, and record an approval. CIDRA never merges: merging the draft pull request is done by a person on GitHub.

---

## 4. Quick Start & Installation

### Option A: Standard PyPI Installation (Recommended)

CIDRA is distributed as a lightweight, pre-packaged Python wheel bundling the compiled web dashboard.

```bash
# Install CIDRA via pip
pip install cidra

# Bring your own key: any OpenAI-compatible endpoint
export CIDRA_API_KEY="..."
export CIDRA_BASE_URL="https://openrouter.ai/api/v1"
export CIDRA_MODEL_ANALYZE="<model id>"
export CIDRA_MODEL_FIX="<model id>"

# Launch the visual dashboard
cidra dashboard
```

### Option B: Local Repository Repair

To diagnose and repair a failing codebase locally without pushing to GitHub:

```bash
# Ensure local Docker daemon is running, then build the sandbox container.
# From a clone:
docker build -t cidra-sandbox:base -f cidra/sandbox/Dockerfile cidra/sandbox
# From a pip install (the Dockerfile ships inside the package):
docker build -t cidra-sandbox:base "$(python -c 'import cidra, os; print(os.path.join(os.path.dirname(cidra.__file__), "sandbox"))')"

# That image runs Python 3.11. If the repository's workflow asks actions/setup-python
# for 3.7-3.10, 3.12 or 3.13 (or has a .python-version file), CIDRA builds a matching
# image the first time it is needed, which takes about a minute.

# Run CIDRA against your local repository
cidra fix
```

### Option C: Terminal User Interface (Rich TUI)

If you are working in a headless server environment without a browser:

```bash
python -m cidra.tui
```

---

## 5. GitHub Actions Integration

CIDRA runs natively inside your GitHub Actions workflows using the `workflow_run` trigger. This eliminates external SaaS dependencies and runs entirely within your runner's security boundaries.

### Dual-Token Security Architecture

To protect production branches from compromised dependencies or malicious PRs:
- **`CIDRA_GITHUB_TOKEN_RO`**: Read-only PAT used to fetch workflow run logs and commit metadata. Optional: when it is not set, the write token is used for reads too.
- **`CIDRA_GITHUB_TOKEN`**: Scoped write PAT used strictly to push verified fix branches and open Draft PRs.

### Complete Workflow (`.github/workflows/cidra.yml`)

```yaml
name: CIDRA Autonomous Repair

on:
  workflow_run:
    workflows: ["CI", "Test Suite"]
    types: [completed]

jobs:
  repair:
    name: Diagnose and Repair
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    permissions:
      contents: write
      pull-requests: write
      actions: read

    steps:
      - name: Checkout Codebase
        uses: actions/checkout@v4
        with:
          # The commit whose CI failed, not the default branch's tip
          ref: ${{ github.event.workflow_run.head_sha }}
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install CIDRA
        run: pip install cidra

      - name: Build Sandbox Image
        # The Dockerfile ships inside the installed package
        run: docker build -t cidra-sandbox:base "$(python -c 'import cidra, os; print(os.path.join(os.path.dirname(cidra.__file__), "sandbox"))')"

      - name: Execute Autonomous Repair
        env:
          CIDRA_API_KEY: ${{ secrets.CIDRA_API_KEY }}
          CIDRA_GITHUB_TOKEN: ${{ secrets.CIDRA_GITHUB_TOKEN }}
          CIDRA_GITHUB_TOKEN_RO: ${{ secrets.CIDRA_GITHUB_TOKEN_RO }}
          CIDRA_ENABLE_PR_CREATION: "true"
        run: cidra action

      - name: Trigger Live Dashboard Rebuild (Vercel)
        if: always()
        run: |
          if [ -n "${{ secrets.VERCEL_DEPLOY_HOOK }}" ]; then
            curl -s -X POST "${{ secrets.VERCEL_DEPLOY_HOOK }}"
          fi
```

### Repository setup for pull requests

- **Allow Actions to open pull requests.** In the repository: Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests". Without it GitHub returns 403: the fix branch is pushed but no PR is opened.
- **Who opens the pull request.** With the built-in `GITHUB_TOKEN` (the default, no setup) the fix PR is opened by `github-actions[bot]` and the fix commit is authored by `CIDRA`. This is the recommended setup: no personal credential is involved.
- **CI on CIDRA's pull requests.** GitHub does not start workflows for a PR opened with the built-in `GITHUB_TOKEN`, so the fix PR shows no checks until a person pushes to it or re-opens it. The fix has already been verified in the sandbox. To get checks automatically, pass a GitHub App installation token as `github_token`; the PR is then opened by that app's bot. A personal access token also works, but the PR then appears to come from that person, so it is not recommended.
- **Where the PR goes.** A fix for a failure on a branch push is opened as a draft PR against that branch. A fix for a failure on an existing pull request is pushed to that PR's branch, and is never force-pushed.
- **Every run leaves a job summary** on the Actions run page with the diagnosis, whatever the outcome. The job fails only when CIDRA itself could not run (no log, no model, no sandbox).

---

## 6. Multi-Tier LLM Fallback Chain

CIDRA is bring-your-own-key. The primary call goes to the endpoint and model you configure. If it fails, CIDRA tries each fallback provider that has a key set, in order. A fallback with no key is skipped, and a permanent error (bad key, unknown model, no credit) moves straight to the next provider.

```mermaid
flowchart TD
    P["<b>Primary</b><br/>CIDRA_BASE_URL + CIDRA_API_KEY<br/>CIDRA_MODEL_ANALYZE / CIDRA_MODEL_FIX"]
    F1["<b>Fallback 1</b><br/>OpenRouter (OPENROUTER_API_KEY_2)"]
    F2["<b>Fallback 2</b><br/>Groq (GROQ_API_KEY)"]
    F3["<b>Fallback 3</b><br/>NVIDIA NIM (NVIDIA_API_KEY_KIMI, NVIDIA_API_KEY_GLM)"]

    P -- "failed" --> F1
    F1 -- "failed or no key" --> F2
    F2 -- "failed or no key" --> F3

    style P fill:#161b22,stroke:#58a6ff,stroke-width:2px,color:#c9d1d9
    style F1 fill:#161b22,stroke:#bc8cff,stroke-width:2px,color:#c9d1d9
    style F2 fill:#161b22,stroke:#f0883e,stroke-width:2px,color:#c9d1d9
    style F3 fill:#161b22,stroke:#3fb950,stroke-width:2px,color:#c9d1d9
```

The fallback model IDs are fixed in [cidra/integrations/llm.py](cidra/integrations/llm.py). Providers retire models; check them against your provider before relying on a fallback.

### Configuration Environment Variables (`.env`)

Copy [.env.example](.env.example) to `.env` to configure your environment:

| Variable | Description | Default |
|---|---|---|
| `CIDRA_API_KEY` | Key for the primary endpoint | *Required* |
| `CIDRA_BASE_URL` | Primary OpenAI-compatible endpoint | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `CIDRA_MODEL_ANALYZE` | Model ID for root cause analysis | `gemini-3.5-flash` |
| `CIDRA_MODEL_FIX` | Model ID for patch generation | `gemini-3.5-flash` |
| `OPENROUTER_API_KEY_2` | OpenRouter fallback key | *Optional* |
| `GROQ_API_KEY` | Groq fallback key | *Optional* |
| `NVIDIA_API_KEY_KIMI` | NVIDIA NIM fallback key | *Optional* |
| `NVIDIA_API_KEY_GLM` | NVIDIA NIM fallback key | *Optional* |
| `CIDRA_GITHUB_TOKEN` | GitHub token with branch and PR write permissions | *Optional (for PRs)* |
| `CIDRA_GITHUB_TOKEN_RO` | Read-only GitHub token for CI logs | *Optional (falls back to the write token)* |
| `CIDRA_ENABLE_PR_CREATION` | Open a draft PR for a verified fix | `false` |
| `CIDRA_WEBHOOK_SECRET` | HMAC SHA256 secret for webhook validation | *Optional (for webhook)* |
| `CIDRA_DASHBOARD_TOKEN` | Token for the dashboard API; required to serve it on a non-loopback host | *Optional* |
| `CIDRA_AUDIT_SIGNING_KEY` | Key that signs the audit manifest; without it the manifest is unsigned | *Optional* |

The flaky-run count (5), the fix-attempt limit (3) and the sandbox timeouts (300 s per test run) are constants in [cidra/config.py](cidra/config.py) and [cidra/sandbox/limits.py](cidra/sandbox/limits.py), not environment settings.

---

## 7. Hardened Sandbox & Threat Model (ADV-01..ADV-08)

The Docker sandbox ([cidra/sandbox/runner.py](cidra/sandbox/runner.py)) is CIDRA's highest blast-radius component. Its isolation boundaries are hardcoded into the runner architecture and cannot be overridden by callers.

```mermaid
flowchart TD
    subgraph Host["Host Operating System (Protected Zone)"]
        H1["Host Secrets & Environment<br/><i>Zero Leakage (ADV-02)</i>"]
        H2["Host Docker Daemon<br/><i>Socket NEVER Mounted (ADV-01)</i>"]
    end
    
    subgraph Sandbox["Hardened Docker Sandbox (Untrusted Execution)"]
        direction TB
        S1["<b>Static Patch Audit Gate (ADV-07)</b><br/>Pre-execution pattern checks"]
        S2["<b>Network Isolation (ADV-03)</b><br/>network_mode='none' during test/verify"]
        S3["<b>User & PID Caps (ADV-04 & ADV-06)</b><br/>UID 1000 (non-root) & pids_limit=256"]
        S4["<b>Resource Limits (ADV-05 & ADV-08)</b><br/>2GB RAM, 1.0 CPU, auto-cleanup on exit"]
        S1 --> S2 --> S3 --> S4
    end
    
    Host -. "Strict Zero-Trust Boundary" .-x Sandbox
    
    style Host fill:#161b22,stroke:#da3633,stroke-width:2px,color:#c9d1d9
    style Sandbox fill:#0d1117,stroke:#238636,stroke-width:2px,color:#c9d1d9
```

Checked by the Docker isolation tests in [tests/integration/test_sandbox.py](tests/integration/test_sandbox.py) and [tests/unit/test_audit.py](tests/unit/test_audit.py).

---

## 8. Testing & Verification Suite

CIDRA maintains high test coverage with automated unit and integration verification suites:

```bash
# 1. Run the server and API tests (47 tests)
pytest tests/server -v

# 2. Run the core unit tests (168 tests: SBFL, patch audit, git ops, LangGraph routing)
#    No Docker, network or API key needed
pytest tests/unit -v

# 3. Run the Docker integration tests against a clone of the practice repo (21 tests)
CIDRA_PRACTICE_REPO=/path/to/cidra-practice pytest tests/integration -v

# 4. Run the Dashboard-to-Backend live wiring test suite
cd dashboard
npm run test:wiring
```

### Test Suite Summary

- **Server Test Suite (`tests/server/`)**: 47 tests (FastAPI endpoints, HMAC signatures, settings persistence, replay safety).
- **Core Unit Suite (`tests/unit/`)**: 168 tests (Ochiai/Tarantula SBFL ranking, patch audit guards, git isolation, flaky detection).
- **Integration Suite (`tests/integration/`)**: 21 tests (real sandbox runs on fixture branches; skipped when `CIDRA_PRACTICE_REPO` is not set).
- **Key-free end-to-end run**: `scripts/fake_llm.py` stands in for the model so the whole pipeline can run without an API key.
- **Wiring Verification (`test-backend-wiring.js`)**: 5 checks (Live latency probes to OpenRouter and Groq, settings round-trip, telemetry parsing).

---

## 9. Repository Structure & Development

The repository is organized cleanly into source, dashboard, documentation, and tests:

```text
cidra/
├── .github/workflows/    # CI and PyPI publishing automation
├── .vscode/              # Editor settings (filters internal caches)
├── cidra/                # Python Core Engine
│   ├── integrations/     # LLM multi-tier clients & GitHub REST API
│   ├── nodes/            # 18 LangGraph nodes (SBFL, fix, audit, report, etc.)
│   ├── sandbox/          # Hardened Docker sandbox (runner.py, limits.py)
│   ├── server/           # FastAPI backend & settings API
│   ├── static/           # Production web dashboard bundle (embedded in wheel)
│   ├── cli.py            # CLI entry points (dashboard, fix, action)
│   ├── config.py         # Central configuration and .env loading
│   ├── graph.py          # LangGraph state machine definition
│   └── state.py          # Pydantic schemas
├── dashboard/            # Modern React + Vite frontend source code
│   ├── src/              # UI components, views, icons, design system tokens
│   ├── vite.config.js    # Direct-to-cidra/static compiler & dev server
│   └── package.json      # Frontend dependencies & wiring test scripts
├── docs/                 # Engineering specs, threat model, API contracts
├── eval/                 # Evaluation harness & benchmark fixtures
├── tests/                # Test suites
│   ├── unit/             # Unit tests (SBFL, patch audit, routing)
│   ├── integration/      # Docker sandbox tests (need the practice repo)
│   └── server/           # API tests (FastAPI, settings, webhook)
├── .env.example          # Template configuration
├── .gitignore            # Clean, standardized ignore rules
├── action.yml            # GitHub Action definition
├── pyproject.toml        # Package & wheel build configuration
└── README.md             # Project documentation
```

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/abhishekKokadwar/CIDRA.git
cd CIDRA

# Install Python package in editable mode with development dependencies
pip install -e ".[dev]"

# Install dashboard frontend dependencies
cd dashboard
npm install

# Start Vite dev server for frontend development
npm run dev

# Compile dashboard directly into cidra/static/
npm run build
```

---

<div align="center">

*Autonomous repair you can actually trust.*

</div>
