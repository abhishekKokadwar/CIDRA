# Research: Security Architecture of Existing CI/CD Autonomous Agents

## Key Findings

### 1. The "Lethal Trifecta" and Supply Chain Attack Vectors
The integration of Large Language Models (LLMs) into Continuous Integration (CI) and Continuous Deployment (CD) pipelines creates a highly elevated attack surface, characterized by security researchers as the **"Lethal Trifecta"**. This vulnerability occurs when an agent simultaneously possesses:
- **Access to private repository data** (read permissions)
- **The ability to execute commands and communicate externally** (write/execute tools and network egress)
- **Exposure to untrusted content** (untrusted PR descriptions, commit messages, issue comments, or branch code)

The severity of this attack surface was demonstrated in the **"Clinejection"** supply chain attack (February 2026) targeting the Cline coding assistant. Attackers chained indirect prompt injection (via a malicious GitHub issue title) with GitHub Actions cache poisoning to achieve unauthenticated remote code execution. The agent blindly executed `npm install`, which triggered a malicious preinstall script. This script exfiltrated the runner's environment variables to an external server. The attacker then used the `Cacheract` tool to poison the repository's shared cache, which was subsequently restored by the highly privileged nightly release workflow, resulting in the theft of publication tokens (`NPM_RELEASE_TOKEN`, `VSCE_PAT`, `OVSX_PAT`) and the compromise of global npm packages.

### 2. Sandbox Isolation vs. In-Runner Execution
A major dividing line exists between agents that run in isolated, dedicated cloud virtual machines (VMs) and those that run directly in the user's existing CI runner (e.g., GitHub Actions runner):
- **Cloud-VM Isolated Agents (Google Jules, Gitar):** These agents clone the repository into dedicated cloud VMs or ephemeral containers (e.g., Google Jules utilizes a 20GB cloud VM; Gitar runs in ephemeral environments destroyed immediately after task completion). This severs the execution context from the host repository's sensitive CI environment, preventing local cache contamination or host secret extraction.
- **In-Runner Agents (Claude Code, GitHub Copilot, OpenAI Codex, Nx Self-Healing CI, FixSense):** These agents execute directly on the user's standard CI runner (e.g., `ubuntu-latest`). While simple to integrate, they run on the same virtual machine that contains sensitive repository secrets and cached dependencies. If the agent executes untrusted code (such as running `npm install` or testing user-submitted code in a PR), a compromised subprocess can access system endpoints (like `/proc/self/environ` or local environment variables) to steal credentials.

### 3. Network Egress and AI Firewall Protections
Without egress controls, an agent manipulated via prompt injection can easily exfiltrate secrets (like `GITHUB_TOKEN` or `ANTHROPIC_API_KEY`) to an external command-and-control server. 
- **GitHub Copilot Cloud Agent** implements a built-in network firewall ("agent firewall") enabled by default, which restricts its outbound connections and blocks arbitrary external requests.
- **Anthropic Claude Code GitHub Action** does not enforce any network restrictions by default. This makes security tools like **StepSecurity Harden-Runner** or **Pipelock** (an AI egress proxy and Model Context Protocol firewall) critical for intercepting outbound traffic and detecting unauthorized exfiltration.
- **FixSense** operates on a **"Bring Your Own Key" (BYOK)** model. The AI API key is configured as a GitHub Actions secret in the user's repository rather than being stored on FixSense SaaS servers. While this keeps keys out of the vendor's database, the key is still exposed to the runner environment during execution.

### 4. Human-In-The-Loop (HITL) and Regulatory Compliance (EU AI Act)
As autonomous agents transition to enterprise pipelines, they intersect directly with global regulatory frameworks, most notably the **EU AI Act** (taking effect in August 2026). 
Under the Act, standard autocomplete tools are categorized as low-risk. However, autonomous agents embedded in CI/CD pipelines that automatically evaluate developer performance, allocate tasks, or act as safety components in critical pipelines are classified as **Annex III High-Risk systems**. 
This classification triggers strict obligations (Articles 8–15), including automatic logging for traceability and mandatory **Human Oversight (Article 14)**. Autonomous agents are legally prohibited from executing irreversible actions without a human intervention or halt mechanism. This validates the design shift away from fully autonomous agent meshes toward **Human-in-the-Loop (HITL)** topologies:
- The agent's final action is strictly restricted to opening a Pull Request (PR) or suggesting a diff.
- A human engineer must review and sign off before code is merged.
- Initial deployments are run in **Shadow Mode**, where the agent's output is recorded in logs to build a baseline of reliability without write permissions.

---

## Sources

| # | Title | Source | Type | Date |
|---|-------|--------|------|------|
| 1 | [Build with Jules, your asynchronous coding agent](https://blog.google/innovation-and-ai/models-and-research/google-labs/jules/) | Google Blog | 📰 News | 2025-12-15 |
| 2 | [Google Jules: The Architecture of Autonomous Cloud Engineering](https://www.youtube.com/watch?v=LKRcjZpJRD4) | YouTube | 🔧 Technical | 2026-01-10 |
| 3 | [Securing CI/CD in an agentic world: Claude Code Github action case](https://www.microsoft.com/en-us/security/blog/2026/06/05/securing-ci-cd-in-agentic-world-claude-code-github-action-case/) | Microsoft Security | 🛡️ Threat Intel | 2026-06-05 |
| 4 | [How to Secure Claude Code in GitHub Actions with Harden-Runner](https://www.stepsecurity.io/blog/anthropics-claude-code-action-security-how-to-secure-claude-code-in-github-actions-with-harden-runner) | StepSecurity | 🔧 Technical | 2026-05-20 |
| 5 | [About GitHub Copilot cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent) | GitHub Docs | 🌐 Overview | 2026-01-20 |
| 6 | [Securing GitHub Copilot in GitHub Actions with Harden-Runner](https://www.stepsecurity.io/blog/securing-github-copilot-in-github-actions-with-harden-runner) | StepSecurity | 🔧 Technical | 2026-04-12 |
| 7 | [Security - openai/codex-action](https://github.com/openai/codex-action/security) | GitHub (OpenAI) | 🔧 Technical | 2026-03-15 |
| 8 | [OpenAI Codex vulnerability enabled GitHub token theft via command injection](https://siliconangle.com/2026/03/30/openai-codex-vulnerability-enabled-github-token-theft-via-command-injection-report-finds/) | SiliconANGLE | 📰 News | 2026-03-30 |
| 9 | [Introducing Self-Healing CI for Nx and Nx Cloud](https://nx.dev/blog/nx-self-healing-ci) | Nx Blog | 📰 News | 2025-11-20 |
| 10 | [Terms of Service — FixSense Docs](https://fix-sense.com/docs/legal/terms-of-service) | FixSense | ⚖️ Legal | 2026-03-03 |
| 11 | [Get started with Gitar AI code review](https://www.sonarsource.com/resources/library/get-started-with-gitar/) | Sonar | 🌐 Overview | 2026-06-14 |
| 12 | [Gitar | AI Code Review That Fixes Your Code](https://docs.gitar.ai/administration/security) | Gitar Docs | 🔧 Technical | 2026-04-10 |

---

## Detailed Notes on Key Agent Architectures

### 1. GitHub Copilot / Copilot Coding Agent + GitHub Actions
* **What can the agent READ?** Repository source code, adjacent PR diffs, Actions failure logs, active issue description, and user chat history.
* **What can the agent WRITE?** Writes code files, creates fix branches, commits modifications, and posts PR reviews or comments.
* **What commands can it EXECUTE?** It executes compile, build, and test steps through GitHub Actions.
* **Does it have NETWORK access?** Yes, but it is restricted by Copilot's built-in **agent firewall** enabled by default. This application-layer firewall restricts outbound connections to unauthorized external endpoints.
* **Can it access SECRETS?** Yes, it can access standard repository secrets and environment variables if they are explicitly passed to the calling Actions job.
* **What GitHub TOKEN permissions does it get?** Standard GitHub Actions `GITHUB_TOKEN` permissions, scoped to the specific repository (typically `contents: write`, `pull-requests: write`, and `issues: write` for creating fix PRs).
* **Where does it run?** Runs directly on the standard GitHub Actions runner (e.g., `ubuntu-latest`).
* **Is the sandbox isolated?** It is isolated to the extent of the GitHub Actions VM itself, but has no additional sandbox boundaries separating Copilot's code-execution steps from adjacent steps in the same runner.
* **How does it handle untrusted PRs?** Relies on standard GitHub repository configuration: workflows triggered by fork PRs are restricted from accessing repository secrets unless explicitly configured via high-risk triggers (like `pull_request_target`).
* **How does it handle prompt injection?** Uses basic prompt filtering. However, researchers recommend wrapping Copilot runs with **StepSecurity Harden-Runner** to provide behavioral intelligence and block outbound egress if an injected script attempts exfiltration.
* **How does it verify a generated fix?** Re-runs the project's native test suite inside the runner and evaluates exit codes.

### 2. Google Jules
* **What can the agent READ?** Full repository clone, active issues, pull requests, comments, and project metadata (e.g., `.cloude` or `AGENTS.md` context files).
* **What can the agent WRITE?** Generates code patches, structures multi-file refactoring steps, and proposes a Pull Request.
* **What commands can it EXECUTE?** Executes shell commands, compiles project binaries, installs dependencies, and runs test commands.
* **Does it have NETWORK access?** Yes, the execution agent can connect to external Model Context Protocol (MCP) servers and dependencies.
* **Can it access SECRETS?** Standard cloud VM setups limit direct access to host repository secrets. The calling Action uses `JULES_API_KEY` for API authentication.
* **What GitHub TOKEN permissions does it get?** Interacts asynchronously with GitHub via GitHub App OAuth tokens scoped strictly to selected repositories.
* **Where does it run?** Runs asynchronously inside dedicated, isolated **Google Cloud Virtual Machines (20GB VM)**. It does *not* execute on the developer's local machine or the repository's standard CI runner.
* **Is the sandbox isolated?** Yes. Every task runs in an isolated cloud VM that is destroyed immediately upon task completion. Jules utilizes "Environment Snapshots" to cache dependency installations to optimize startup speeds.
* **How does it handle untrusted PRs?** Since Jules operates asynchronously and delivers changes as an external PR, its outputs are entirely governed by branch protection rules and mandatory human code reviews.
* **How does it handle prompt injection?** Utilizes a multi-agent **Critique Agent** (Critic-Augmented Generation) powered by Gemini. The Critique Agent performs adversarial peer review to screen for security vulnerabilities, malicious dependencies, and logic errors before any code is tested or written.
* **How does it verify a generated fix?** Uses a "Testing Agent" that executes native test suites in the Cloud VM and leverages multimodal vision to verify frontend UI rendering.

### 3. OpenAI Codex (openai/codex-action)
* **What can the agent READ?** Diffs, pull request titles, pull request bodies, commit messages, and repository instruction files (such as `AGENTS.md` or `AGENTS.override.md`).
* **What can the agent WRITE?** Writes unified diffs and PR comments.
* **What commands can it EXECUTE?** Executes the `codex exec` command under specific permission profiles.
* **Does it have NETWORK access?** Configurable via the `permission-profile` input, which controls filesystem and network boundaries.
* **Can it access SECRETS?** Requires the `OPENAI_API_KEY`.
* **What GitHub TOKEN permissions does it get?** Restricts permissions to the minimum necessary: `contents: read` for analysis, transferring output to a secondary, lower-privilege runner to handle issues/PR comments (`issues: write`, `pull-requests: write`).
* **Where does it run?** Executes on the repository's GitHub Actions runner (e.g., `ubuntu-latest`).
* **Is the sandbox isolated?** Operates under configurable sandbox profiles: `workspace-write`, `read-only`, and `danger-full-access`.
* **How does it handle untrusted PRs?** Strongly warns against using `pull_request_target`. Pinning all sub-actions to immutable SHA commit hashes is required. Integrates `allow-users` or `allow-bots` filters to prevent unauthorized external actors from triggering analysis on PRs.
* **How does it handle prompt injection?** Prompt injection remains an acute threat. In March 2026, researchers demonstrated that an obfuscated command injection exploit in Codex's local CLI and actions could result in GitHub OAuth token compromise.
* **How does it verify a generated fix?** Does not natively compile or verify code; instead, it outputs diff suggestions to be validated by downstream CI test jobs.

### 4. Anthropic Claude Code GitHub Action (anthropics/claude-code-action)
* **What can the agent READ?** Codebase files, issue/PR descriptions, user comments, and environment paths.
* **What can the agent WRITE?** Modifies files directly in the working directory, creates commits, and writes PR feedback.
* **What commands can it EXECUTE?** Executes arbitrary shell commands via the `Bash` tool (e.g., executing test suites, build scripts).
* **Does it have NETWORK access?** Yes, it operates with full outbound network access by default.
* **Can it access SECRETS?** Yes, it can access the runner's environment variables. In mid-2026, Microsoft Threat Intelligence disclosed a vulnerability where Claude's `Read` tool could bypass the Bash sandbox to read `/proc/self/environ`, exposing `ANTHROPIC_API_KEY` and other workflow secrets. This was patched by Anthropic.
* **What GitHub TOKEN permissions does it get?** Requires standard GitHub Action write permissions (`contents: write`, `pull-requests: write`) to automatically commit fixes.
* **Where does it run?** Runs directly on the calling repository's GitHub Actions runner VM.
* **Is the sandbox isolated?** No. It runs directly inside the host VM. It uses the `--dangerously-skip-permissions` flag to allow Claude to write files without manual prompt approvals.
* **How does it handle untrusted PRs?** To prevent untrusted fork PRs from modifying configurations or stealing keys, the action checks actor permissions, restricts execution to authorized users, and automatically restores project configuration files (like `.claude/` or `CLAUDE.md`) from the base branch ref in PR contexts.
* **How does it handle prompt injection?** Vulnerable to indirect prompt injections embedded in issues or pull requests. Security guidance recommends using an AI egress proxy (like Pipelock) to monitor and block exfiltration or restricting Claude's tools via `--allowedTools "Bash(git:*),Read,Glob,Grep"`.
* **How does it verify a generated fix?** Relies on the runner executing the project's native test commands after a patch is applied.

### 5. Nx Self-Healing CI (Nx Cloud)
* **What can the agent READ?** The Nx workspace structure, workspace dependencies, project task graphs, and raw CI logs.
* **What can the agent WRITE?** Writes code files to resolve build failures (e.g., missing imports, dependency definitions, or syntax errors) and generates diagnostic PR comments.
* **What commands can it EXECUTE?** Executes build, test, and lint tasks within the Nx monorepo.
* **Does it have NETWORK access?** Yes, it connects to Nx Cloud and OpenAI/Gemini endpoints.
* **Can it access SECRETS?** Access is limited to standard repository secrets required to connect to Nx Cloud.
* **What GitHub TOKEN permissions does it get?** Uses standard VCS integration permissions (via GitHub App or GITHUB_TOKEN).
* **Where does it run?** Executes within the existing CI pipeline execution context on your runner.
* **Is the sandbox isolated?** No additional VM isolation is provided; it operates within your existing, ephemeral CI runner VM.
* **How does it handle untrusted PRs?** Triggered only by authorized repository events (commits from approved branch authors).
* **How does it handle prompt injection?** Low risk of traditional prompt injection because the agent processes structured Nx workspace graphs and compiler/build logs rather than parsing raw natural language from issue boards.
* **How does it verify a generated fix?** Highly sophisticated verification: deeply integrated with the **Nx task graph**, it applies the proposed patch and re-runs *only the specific, affected projects and downstream checks* within the same pipeline execution. It outputs the complete decision trace directly to the PR.

### 6. Harness AI CI Agents (Harness AutoFix / AIDA)
* **What can the agent READ?** Pipeline configurations, historical deployment logs, CD build telemetry, application metrics, and APM data.
* **What can the agent WRITE?** Modifies CI/CD pipeline YAML files, generates code patches, and updates deployment scripts.
* **What commands can it EXECUTE?** Triggers automated deployment rollbacks, executes pre-flight checks, and initiates test runner retries.
* **Does it have NETWORK access?** Yes, connects to Harness SaaS and customer-managed cloud environments.
* **Can it access SECRETS?** Integrates with Harness's built-in, secure secrets manager (HashiCorp Vault, OIDC) to fetch credentials dynamically without exposing them in plaintext.
* **What GitHub TOKEN permissions does it get?** Leverages OIDC and granular repository RBAC settings.
* **Where does it run?** Runs on Harness-hosted or customer-hosted delegates (private execution environments).
* **Is the sandbox isolated?** Delegates execute tasks in dedicated, isolated container or virtual machine boundaries.
* **How does it handle untrusted PRs?** Enforces strict continuous delivery governance. High-risk steps (like production deployments or architectural changes) require human sign-off.
* **How does it handle prompt injection?** Uses **Open Policy Agent (OPA)** policy-as-code engines to evaluate and validate generated patches, ensuring compliance with organizational security rules before execution.
* **How does it verify a generated fix?** Uses multi-stage verification, executing pre-flight checks, automated rollbacks on failure, and post-deployment validation.

### 7. FixSense
* **What can the agent READ?** JUnit XML test reports, execution stack traces, error logs, and screenshots. **FixSense does not access, read, or store the user's source code on its SaaS servers.**
* **What can the agent WRITE?** Writes root-cause analyses into PR comments and creates dedicated fix branches.
* **What commands can it EXECUTE?** Runs auto-fix scripts entirely within your local CI runner.
* **Does it have NETWORK access?** Connects to the FixSense SaaS backend for failure telemetry and diagnostic parsing.
* **Can it access SECRETS?** Uses a **"Bring Your Own Key" (BYOK)** model. The user's AI API key (Anthropic or OpenAI) is configured as a GitHub Actions secret in the user's repository, ensuring FixSense never stores API keys on its SaaS database.
* **What GitHub TOKEN permissions does it get?** Uses basic repository write tokens to push fix branches and post PR feedback.
* **Where does it run?** Runs directly within your own repository's CI runner VM.
* **Is the sandbox isolated?** Subject only to the default isolation of the host CI runner.
* **How does it handle untrusted PRs?** Standard GITHUB_TOKEN safety restrictions apply.
* **How does it handle prompt injection?** Safe from direct repository code poisoning because it processes test metadata rather than unconstrained codebase files. However, the LLM running on the runner is theoretically vulnerable to prompt injections hidden in failing test outputs.
* **How does it verify a generated fix?** Executes iterative test commands inside the CI runner until all failing tests pass before creating a fix PR.

### 8. Gitar
* **What can the agent READ?** Repository source code, PR diffs, and historical CI logs. Gitar has zero data retention policies and does not retain code or use it to train models.
* **What can the agent WRITE?** Inline PR comments, consolidated dashboard comments, and code commits directly back to the active branch.
* **What commands can it EXECUTE?** Compiles, lint-checks, and tests code files during the review process.
* **Does it have NETWORK access?** Yes, connects to Gitar's cloud orchestrator and LLM provider endpoints.
* **Can it access SECRETS?** Integrates via standard VCS OAuth permissions.
* **What GitHub TOKEN permissions does it get?** Installs as a GitHub App with granular permissions (`pull-requests: write`, `contents: write`).
* **Where does it run?** Runs in ephemeral cloud environments that are destroyed immediately after completing tasks (managed by Gitar/Sonar).
* **Is the sandbox isolated?** Yes, runs in isolated, ephemeral container environments.
* **How does it handle untrusted PRs?** Employs a **Human-in-the-Loop (HITL)** design: the agent posts suggestions as PR comments, and a developer must explicitly check a box on GitHub to authorize Gitar to commit the fix.
* **How does it handle prompt injection?** Following its acquisition by **Sonar in May 2026**, Gitar integrates SonarQube's multi-layered static and dynamic code verification. It validates all LLM output against rigorous syntax, logic, and data flow models before applying them, neutralizing prompt injection payloads.
* **How does it verify a generated fix?** Gitar is deeply integrated with the repository's native CI pipeline. It validates every proposed change against the actual CI pipeline and will not commit any fix that fails the build.

---

*Research conducted on September 5, 2026.*
