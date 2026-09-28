# Deployment & Distribution Plan — CIDRA

> **Scope:** How to take CIDRA from a local development environment to a production-ready, zero-infrastructure deployment by leveraging GitHub Actions and PyPI, while maintaining strict security boundaries.

This document outlines the practical release path for CIDRA, pivoting away from self-hosted cloud VMs (like Oracle/AWS) toward a frictionless, user-driven execution model.

---

## 1. Primary Release Path: GitHub Actions Native Action

Instead of hosting a central webhook server that users must trust, CIDRA will be packaged to run natively as a GitHub Action within the user's own repository. This provides massive, zero-cost compute (via GitHub's runners) and keeps API keys completely under the user's control.

### Step 1.1: Minimal Diagnostic Action (v0.1)
*   **Environment:** Runs on `ubuntu-latest`.
*   **Functionality:** Wakes up on a failed workflow, ingests logs, spins up the CIDRA Docker sandbox (using the runner's native Docker environment), and posts a structured diagnosis as a PR/issue comment.
*   **Permissions:** Narrowly scoped. Requires `contents: read` (to check out code) and `pull-requests: write` (to post the diagnostic summary). 
*   **Feature Gate:** Draft Pull Request creation is disabled in this phase. It will only be added after the workflow can be reviewed and approved safely in the wild.

### Step 1.2: Actions Security & Isolation
Running untrusted code (the user's failing tests) on a runner that also holds a secret (`CIDRA_API_KEY`) requires extreme care. GitHub explicitly warns against combining privileged workflows, secrets, and untrusted code checkout.
*   **Mitigation:** CIDRA's existing architecture already confines the untrusted code to a non-privileged, network-isolated Docker container (`cidra-sandbox:base`). 
*   **Workflow Constraints:** We will explicitly document how to configure the action for fork PRs. If used via `pull_request_target` (which exposes secrets), we rely entirely on the Phase 4 sandbox hardening to prevent exfiltration.

### Step 1.3: User Limits & Documentation
Users must be clearly informed of the costs of running an autonomous agent:
*   **Actions Allowance:** The Docker sandbox and iterative fix loops run on the user's GitHub runner and will consume their GitHub Actions minute allowance.
*   **LLM Costs:** The user supplies their own API key (BYOK) and is responsible for provider costs.

---

## 2. Secondary Release Path: PyPI & Local CLI

Publishing CIDRA as a Python package enables the GitHub Action, but also unlocks a powerful second use-case: developers running CIDRA directly on their laptops while coding, entirely independent of CI.

### Step 2.1: PyPI Trusted Publishing
*   CIDRA will be published to PyPI using [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/). 
*   This uses GitHub Actions (OIDC) to authenticate with PyPI, meaning releases happen automatically on git tags without needing to manage or store long-lived PyPI tokens.

### Step 2.2: The Local CLI Tool
*   Developers can `pip install cidra` globally.
*   When a local test fails, they can run `cidra fix` in their terminal to diagnose and repair the code locally before ever pushing to GitHub.

---

## 3. Immediate Prerequisites (The "To-Do" List)

Before either release path can be executed, the project needs structural updates:

1.  **Installable Package Metadata (`pyproject.toml`)**
    *   *Current State:* The project relies on a flat `requirements.txt` and is not installable.
    *   *Action:* Create a root `pyproject.toml` (using Hatch or Poetry). Define CIDRA as a standard Python package.
    *   *Action:* Define console entrypoints (e.g., `cidra = "cidra.cli:main"`).
2.  **Documented User Setup**
    *   *Current State:* The README is geared toward developing CIDRA itself.
    *   *Action:* Write a user-facing setup guide explaining how to acquire the LLM key, how to add the Action to their `.github/workflows/`, and how to install the CLI locally.
3.  **CLI Entrypoint Refactoring**
    *   Separate the core graph execution from the webhook server (`app.py`), allowing it to be invoked cleanly via the CLI or the GitHub Action runner script.
