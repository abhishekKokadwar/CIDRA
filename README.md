# CIDRA

**C**ontinuous **I**ntegration **D**ebugging and **R**epair **A**gent.

A LangGraph agent that triggers on CI failure, diagnoses the root cause, reproduces it
in a hardened Docker sandbox, and **only claims a fix it has verified green**.

The interesting claim is not "AI fixes CI" — plenty of tools say that. It is that this
one is measured: a fixture corpus with hand-written ground truth, an adversarial sandbox
test set, and a refusal path for failures it cannot honestly repair.

## Status

Work in progress, built in phases (see [docs/3_phases.md](docs/3_phases.md)).

| Phase | State |
|---|---|
| 0 — Skeleton + 18-node graph | done |
| 1 — Fixture corpus | done (logs are local; real CI logs pending) |
| 2 — Log ingestion | isolation done; GitHub API fetch pending |
| 3 — LLM root-cause analysis | done — 7/7 category accuracy |
| 4 — Docker sandbox | done — 7/7 fixtures reproduce red |
| 5 — Fix + verify loop | done |
| 6 — Output + safety | done |
| 7 — Live webhook / GitHub Action | planned (Action integration) |
| 8+ — Extensibility & Enterprise features | in progress |

## What works today

Running the full graph against real fixtures, on real Docker:

| Fixture | Class | Outcome |
|---|---|---|
| F-01 | missing_dependency | `verified_fix` — red, patched, green |
| F-04 | flaky_test | `flaky_detected` — **0 fix attempts** |
| N-01 | out of scope | `diagnosis_only` — **0 LLM calls**, no fix claimed |
| bad patch | — | `verified: false` — never claims an unapplied fix |

Flaky tests get a first-class terminal outcome rather than being forced through a
fix-verify cycle they can never satisfy.

## Safety

The sandbox is the highest blast-radius component, so its rules are enforced in
[cidra/sandbox/runner.py](cidra/sandbox/runner.py) rather than left to callers — there is
no `privileged` parameter, no `network` parameter, and no way to override the resource caps
from a call site. Full threat model in [docs/6_sandbox_spec.md](docs/6_sandbox_spec.md).

Verified by [test_sandbox.py](test_sandbox.py) (15 checks): no network during test/verify,
network only during dependency install, no Docker socket, no host secrets in the container,
non-root, timeouts enforced, fork bombs bounded by `pids_limit`, containers always removed.

**LLM output is data, never code.** The model returns a unified diff, applied with
`git apply`. Test commands are CIDRA-authored constants.

## Installation & Setup

CIDRA is distributed as a standard Python package. You can run it locally as a CLI debugging assistant, or plug it into your GitHub Actions for autonomous CI repairs.

### 1. Local CLI Dev Tool

Diagnose and repair your code locally before pushing to CI.

```bash
# Install the package
pip install cidra

# Configure your LLM Provider key (e.g. Gemini, OpenAI, Anthropic)
export CIDRA_API_KEY="your-api-key"

# Ensure the local Docker daemon is running, then build the sandbox base image:
docker build -t cidra-sandbox:base -f cidra/sandbox/Dockerfile cidra/sandbox

# Run CIDRA against your local codebase
cidra fix
```

### 2. GitHub Actions Integration (Coming Soon)

CIDRA can be plugged natively into your `.github/workflows/`. Because it runs inside your runner, you pay zero infrastructure costs. 

```yaml
jobs:
  test-and-repair:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run CIDRA
        uses: cidra-ai/cidra-action@v1
        env:
          CIDRA_API_KEY: ${{ secrets.CIDRA_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```
*Note: To protect your API keys, CIDRA strictly isolates the untrusted checkout environment from the orchestration layer.*

## Developing CIDRA

To develop the agent itself:
```bash
pip install -e ".[dev]"
cp .env.example .env

# Run the test suite
pytest tests/
python eval/run_eval.py --tier 1
```

## Docs

| | |
|---|---|
| [1_project_understanding.md](docs/1_project_understanding.md) | The original brief |
| [2_scope_and_decisions.md](docs/2_scope_and_decisions.md) | What's in, what's out, and why |
| [3_phases.md](docs/3_phases.md) | Build order |
| [4_architecture.md](docs/4_architecture.md) | Graph topology, state, trust boundaries |
| [5_fixtures.md](docs/5_fixtures.md) | Fixture corpus + eval methodology |
| [6_sandbox_spec.md](docs/6_sandbox_spec.md) | Threat model and container rules |
