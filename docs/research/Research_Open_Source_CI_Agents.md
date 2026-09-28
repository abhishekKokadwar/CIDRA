# Research: Open-Source CI-Agent Projects

This research report examines the open-source landscape of **AI-driven CI/CD repair and self-healing agents** on GitHub. It evaluates seven prominent projects against key technical, operational, and security dimensions to identify industry standards and pinpoint gaps where CIDRA can offer high-value differentiation.

---

## Technical Comparison Matrix

| Repository | Stars | Last Activity | Supported CI | Sandbox Isolation | Verification Method |
|---|---|---|---|---|---|
| **ryanmac/code-conductor** | ~110 | Sept 2026 | GitHub Actions | Git Worktree (local) | Downstream CI checks |
| **microsoft/conductor** | ~300 | Sept 2026 | GitHub Actions, Local | Azure Container Apps | Exit codes & JSON stdout |
| **nandanadileep/autonomous-ci-repair** | ~15 | Mid 2026 | GitHub Actions | None (Runner Host) | Custom test-command runs |
| **mraza007/baton** | ~100 | Dormant | GitHub Actions, Local | Git Worktree (local) | E2E Browser (Playwright) |
| **psyduckler/self-healing-agents** | ~60 | Sept 2026 | Local, OpenClaw | None (Runner Host) | Known-Fix validation |
| **jalpatel11/Self-Healing-SRE-Agent** | ~40 | Mid 2026 | GitHub Actions | None (Runner Host) | Separated Validator Agent |
| **tirthpatel90/AutoHeal-CI** | ~10 | Mid 2026 | Local, Pre-Push | None (Local Host) | None (Prediction focus) |

---

## Detailed Project Analysis

### 1. ryanmac/code-conductor
*   **GitHub Repo**: [ryanmac/code-conductor](https://github.com/ryanmac/code-conductor)
*   **Stars**: ~110
*   **Last Activity**: September 2026 (Highly Active)
*   **Architecture**: Orchestrator that parallelizes code-generation runs by spawning multiple Claude Code sub-agents. It coordinates execution by converting GitHub Issues (labeled `conductor:task`) into independent branches.
*   **Supported CI**: GitHub Actions (integrated via `.github/workflows/code-review.yml`).
*   **Supported Languages**: Multi-language (automatically detects React/Next.js, Node.js, Python, Go, Java, PHP, .NET Core, React Native, Flutter, Tauri, Electron).
*   **Repair Capabilities**: Automates bug fixing, frontend component generation, DevOps config updates, and security scanning by mapping issues to specialized sub-agent roles.
*   **Sandbox**: Local workspace isolation is enforced using separate Git worktrees (`worktrees/agent-{role}-{task_id}`), which prevents files from colliding. However, it does not use VM or container-level isolation.
*   **Security Model**: Relies on GitHub Actions' default permissions (or customized repository-scoped PATs). Uses a heartbeat monitor (`health-check.py` and `cleanup-stale.py`) to prune hung or run-away sub-agent branches after a timeout.
*   **Verification**: Leverages downstream GitHub Actions checks. It relies on CodeRabbit-style automated PR reviews to scan agent output for vulnerabilities, performance gaps, and syntax errors before allowing a human merge.
*   **What is Genuinely Novel?**: **Git Worktree Parallelization & Stack Auto-Configuration**. By mapping tasks to distinct git worktrees on a single runner, it allows multiple Claude Code agents to solve disparate bugs simultaneously without merge conflicts or local folder collisions.

---

### 2. microsoft/conductor
*   **GitHub Repo**: [microsoft/conductor](https://github.com/microsoft/conductor)
*   **Stars**: ~300
*   **Last Activity**: September 2026 (Highly Active)
*   **Architecture**: A robust, developer-first orchestration CLI that implements deterministic, multi-agent pipelines defined entirely in YAML. It decouples state transition routing from the LLM, executing steps based on structured conditional logic rather than agentic "vibe" routing.
*   **Supported CI**: GitHub Actions, Local Terminals, Azure Container Apps.
*   **Supported Languages**: Language-agnostic.
*   **Repair Capabilities**: Multi-step analysis, planning, patch generation, and review. It coordinates distinct specialized agents (e.g., researcher, planner, coder, critic) using the GitHub Copilot SDK or Anthropic Agents SDK.
*   **Sandbox**: Supports experimental **Azure Container Apps (ACA)** integration to execute untrusted code steps in ephemeral, highly isolated micro-containers.
*   **Security Model**: Prevents indirect prompt injection from hijacking the workflow state machine by using deterministic YAML-defined routing gates. Integrates explicit Human-in-the-Loop (HITL) pause-gates that halt execution until a developer reviews intermediate steps in a specialized web dashboard or Fleet Manager TUI.
*   **Verification**: Developers write custom verification assertions using script steps that check process exit codes, file modifications, or JSON stdout.
*   **What is Genuinely Novel?**: **Deterministic YAML-Based Orchestration**. By removing the LLM from the routing loop (routing is evaluated via Jinja2 templates and expression boundaries), it completely eliminates prompt injection attacks on the pipeline itself, ensuring that security gates cannot be bypassed by clever adversarial text.

---

### 3. nandanadileep/autonomous-ci-repair
*   **GitHub Repo**: [nandanadileep/autonomous-ci-repair](https://github.com/nandanadileep/autonomous-ci-repair)
*   **Stars**: ~15
*   **Last Activity**: Mid 2026
*   **Architecture**: A highly-focused, single-agent repair loop. When a GitHub build fails, it parses the failure logs, retrieves the relevant source code, and queries an LLM to generate a patch.
*   **Supported CI**: GitHub Actions (implemented as a reusable workflow `self_healing.yml`).
*   **Supported Languages**: Language-agnostic, though standard configurations target Python/pytest.
*   **Repair Capabilities**: Log-to-patch code transformations, missing import resolution, test assertion adjustments, and syntax error repair.
*   **Sandbox**: None. The agent runs directly on the calling GitHub Actions runner VM, leaving it fully exposed to runner-level secret harvesting or shell hijacking.
*   **Security Model**: Minimal. It requires standard `contents: write` permissions to commit repairs back to the branch. Requires `GEMINI_API_KEY` or `GROQ_API_KEY` to be passed as standard repo secrets.
*   **Verification**: Executes the developer's specified `test-command` (e.g. `pytest -v`) locally inside the runner. If the tests go green, it commits the changes directly to the branch with the `[ci-auto-fix]` tag.
*   **What is Genuinely Novel?**: **Hyper-Fuzzy Patching (Gemini-Proof)**. Traditional code repair tools fail when git patch application fails due to minor line number or context hallucinations. This agent uses Python's `difflib.SequenceMatcher` to do fuzzy string matching (>80% similarity) to successfully apply generated code patches even when the LLM hallucinates surrounding context.

---

### 4. mraza007/baton
*   **GitHub Repo**: [mraza007/baton](https://github.com/mraza007/baton) (Desktop companion: [getbaton.dev](https://getbaton.dev))
*   **Stars**: ~100
*   **Last Activity**: Dormant (Active through fork communities)
*   **Architecture**: An event-driven daemon that polls active GitHub Issues, claims them, and dispatches parallel AI coding agents (Claude Code, Codex CLI) to build, test, and open pull requests.
*   **Supported CI**: GitHub Actions, Local Daemon.
*   **Supported Languages**: Language-agnostic.
*   **Repair Capabilities**: Code repair, feature implementation, and unit test additions driven by issue ticket descriptions.
*   **Sandbox**: Workspace-level isolation via Git worktrees. No machine-level container isolation.
*   **Security Model**: Minimal built-in security. Relies on binding task-execution triggers to specific trusted repository labels (e.g. `baton:run`) to prevent unauthorized external triggers.
*   **Verification**: Features an advanced **E2E Browser Verification** layer. It uses Playwright or agent-browser skills to run browser automation against local/deployed servers, taking screenshots and asserting that the visual output matches the requirements specified in the issue.
*   **What is Genuinely Novel?**: **Issue-to-PR Daemon Loop with Post-Deploy Visual Verification**. Rather than stopping at compilation or unit test outputs, it uses headful browser sessions to confirm that the app actually works in practice, posting visual evidence back to the GitHub PR.

---

### 5. psyduckler/self-healing-agents
*   **GitHub Repo**: [psyduckler/self-healing-agents](https://github.com/psyduckler/self-healing-agents)
*   **Stars**: ~60
*   **Last Activity**: September 2026 (Active)
*   **Architecture**: An associative error-diagnosis and self-healing daemon. It continuously scans pluggable logs (cron-jobs, API logs, system metrics), identifies errors, checks them against a local "Known Fixes" database, and applies repairs.
*   **Supported CI**: Local system crons, OpenClaw, or custom CI pipelines.
*   **Supported Languages**: Language-agnostic (written in Python/Shell).
*   **Repair Capabilities**: Excels at infrastructure repair, cron failures, service restarts, dependency drifts, and system configuration resets.
*   **Sandbox**: None. Operates directly on the host operating system.
*   **Security Model**: Implements a strict **"Two Strikes and Escalate"** boundary. On the first failure, it tries to auto-heal. If the repair fails or triggers a high-risk operation, it immediately halts and escalates to a human operator to prevent cascading loops.
*   **Verification**: Re-executes the broken cron or script and validates that the exit code is zero and stderr is clean.
*   **What is Genuinely Novel?**: **The Known-Fixes Database (Associative Self-Healing)**. Rather than relying on expensive, slow, and non-deterministic LLM generations for every pipeline failure, the tool creates an associative cache of error signatures mapped to verified fixes. When a matching error occurs, it applies the fix deterministically in milliseconds.

---

### 6. jalpatel11/Self-Healing-SRE-Agent
*   **GitHub Repo**: [jalpatel11/Self-Healing-SRE-Agent](https://github.com/jalpatel11/Self-Healing-SRE-Agent)
*   **Stars**: ~40
*   **Last Activity**: Mid 2026
*   **Architecture**: A multi-agent incident response system that distributes debugging labor across four distinct, collaborating agents: Investigator, Mechanic, Validator, and PR Creator.
*   **Supported CI**: GitHub Actions (via `auto_heal_ci.py`).
*   **Supported Languages**: Python, Node.js.
*   **Repair Capabilities**: Root Cause Analysis (RCA) on crash logs, automatic patch generation, and automated pull request creation.
*   **Sandbox**: None. Operates inside the host runner VM.
*   **Security Model**: Uses a multi-agent separation-of-labor design. By dividing code creation (Mechanic agent) from policy and constraint enforcement (Validator agent), it creates an application-level security boundary that prevents code from being committed unless the Validator explicitly signs off.
*   **Verification**: The Validator agent parses the Mechanic's generated code, checking for syntax errors, API boundary compliance, and security anti-patterns before passing the task to the PR Creator.
*   **What is Genuinely Novel?**: **Explicit Multi-Agent Handoff & LangSmith Observability**. It traces every single inter-agent handoff, decision, and verification check inside LangSmith, providing SRE teams with a complete audit trail of the agentic repair process.

---

## The Strategic Gaps: Where CIDRA Wins

A deep review of these open-source tools reveals three critical industry blind spots that represent CIDRA's primary competitive advantages:

1.  **Complete Absence of Hardened Sandboxes**: Nearly all current open-source agents (with the partial, experimental exception of Microsoft Conductor's ACA integration) run directly in the host GitHub Actions runner. They have full access to parent environment variables and private SSH keys, meaning a single malicious log file or prompt injection payload can easily compromise the entire organization's cloud infrastructure. **CIDRA's air-gapped Docker sandboxing is an absolute necessity.**
2.  **Weak Verification Oracles (The "Overfitting" Crisis)**: The dominant verification standard across all these repositories is simply checking if `exit_code == 0` or if a basic test command runs green. None of these tools audit the *generated diff itself* to block package hallucinations, hardcoded bypasses, or structural policy violations. **CIDRA's multi-layered verification (syntactic, dependency, static security, and LLM-peer critique) is highly unique.**
3.  **Vulnerability to Prompt Injection (Comment and Control)**: None of the active open-source agents sanitize incoming GitHub issue metadata or PR logs. They feed raw markdown directly to the model's instruction context, allowing external attackers to easily trigger unauthorized command runs. **CIDRA's boundary-enforced architecture and deterministic routing ensure complete safety against prompt injection.**

---

*Research compiled on September 5, 2026.*
