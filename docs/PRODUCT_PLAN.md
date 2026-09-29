# CIDRA Product Plan: Self-Hosted Enterprise CI Remediation Engine

> **Document Version:** 2.0.0  
> **Status:** Approved Architectural Roadmap  
> **Target Audience:** Engineering Leadership, DevSecOps, Platform Engineering Teams, Enterprise Architects  
> **Core Proposition:** *Self-hosted, air-gapped autonomous CI remediation engine with zero-trust container containment, mathematical fault localization, and deterministic patch verification.*

---

## 1. Executive Summary & Strategic Shift

### 1.1 The Market Paradox
The AI developer tooling landscape is saturated with "cloud-hosted coding bots" that promise to fix any bug from an issue description. However, **enterprise engineering teams (fintech, healthcare, defense, enterprise B2B SaaS) cannot and will not use them**. 

Enterprises face an immutable wall:
1. **Data Loss Prevention (DLP) & Compliance**: SOC 2 Type II, ISO 27001, HIPAA, and customer NDAs prohibit transmitting proprietary source code or CI logs to third-party SaaS AI vendors.
2. **CI Pipeline Poisoning Risks**: Granting an external AI agent write access to GitHub Actions or letting it run uninspected code inside a production CI runner creates a catastrophic supply-chain attack vector (exfiltration of cloud credentials, poisoned dependencies, lateral network movement).
3. **The "Hallucination Tax"**: Generic AI bots attempt to solve complex business logic bugs, generate subtly broken diffs, and burn human engineering hours reviewing bad PRs.

### 1.2 The Strategic Pivot
CIDRA explicitly abandons the "generic SaaS GitHub bot" category. Instead, CIDRA is positioned as:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CIDRA ENTERPRISE POSITIONING                         │
├────────────────────────────────────────────────────────────────────────┤
│ "The self-hosted, air-gapped CI janitor that deterministically repairs │
│ routine build/test failures inside an isolated, zero-network sandbox,  │
│ while strictly refusing ambiguous logic changes and generating signed │
│ compliance audit receipts."                                            │
└────────────────────────────────────────────────────────────────────────┘
```

The BYOK (Bring Your Own Key) / On-Premises architecture is not a temporary missing backend; **it is the primary product moat and selling proposition**.

---

## 2. Situation Analysis: Current State vs. Enterprise Needs

### 2.1 What CIDRA Has Today (The Foundation)
CIDRA v1.0 possesses a differentiated, technically rigorous core that sets it apart from simple prompt wrappers:

- **Mathematical Spectrum-Based Fault Localization (SBFL)**: Implements Ochiai and Tarantula formulas ([cidra/localization/sbfl.py](file:///d:/CODES/cidra/cidra/localization/sbfl.py)) to rank faulty statements via test coverage matrices rather than blindly dumping 200,000 log tokens into an LLM.
- **Hardened Zero-Trust Docker Sandbox**: Enforces non-root execution, dropped capabilities (`CAP_DROP=ALL`), absolute denial of host Docker socket mounting, and `network_disabled=True` during test execution ([cidra/sandbox/runner.py](file:///d:/CODES/cidra/cidra/sandbox/runner.py)).
- **Pre-Execution AST Security Gate**: Static analysis engine ([cidra/auditor/gate.py](file:///d:/CODES/cidra/cidra/auditor/gate.py)) that validates abstract syntax trees before execution, blocking `eval()`, `exec()`, `os.system()`, `subprocess`, socket connections, and malicious imports.
- **Statistical Binomial Flakiness Gate (SR-08)**: 5-run binomial distribution test ([cidra/engine/flakiness.py](file:///d:/CODES/cidra/cidra/engine/flakiness.py)) that detects non-deterministic failures and burns 0 fix attempts on flaky tests.
- **Deterministic Fix Deduplication**: SHA-256 fingerprinting cache (`cidra_fix_cache.json`) enabling zero-token, instant replays for identical recurring failures.
- **Interactive Command Center**: Real-time telemetry dashboard ([dashboard/](file:///d:/CODES/cidra/dashboard)) featuring telemetry visualization, Human-in-the-Loop review gates, and live viewer capabilities.

---

### 2.2 The Gaps: What Exists vs. What Enterprise Requires

| Dimension | Current Implementation (v1.0) | Enterprise Requirement | Problem / Risk in Enterprise Context |
| :--- | :--- | :--- | :--- |
| **Language Support** | Python only (`pytest`, `requirements.txt`, `pyproject.toml`) | Polyglot: TypeScript/Node (`jest`/`vitest`), Go (`go test`), Java (`gradle`/`maven`) | 80%+ of enterprise repositories are multi-language or full-stack monorepos. |
| **Security Boundaries** | Static AST rule check on code | Declarative Policy Engine (`cidra.policy.yml`) with path restrictions and allowlists | SecOps cannot prevent CIDRA from proposing modifications to `/auth`, `/payments`, or DB migrations. |
| **LLM Execution** | Cloud API calls (OpenRouter, Groq, NVIDIA NIM) | Certified `--air-gapped` mode with local Ollama, vLLM, and VPC Private Endpoints | Corporate egress firewalls block outbound calls to public LLM gateway APIs. |
| **Compliance & Audit** | Local JSONL telemetry run history | Signed cryptographic audit manifests (`cidra_audit_manifest.json`) | Security auditors cannot prove the AI didn't phone home or inject backdoor dependencies during CI. |
| **Packaging & Deployment** | CLI tool + local npm Vite server | Turnkey Self-Hosted GitHub Action, Docker Compose, and Kubernetes Helm Chart | Enterprise DevOps cannot deploy or manage CIDRA as a standardized platform daemon. |

---

## 3. Target Customer Profile (ICP) & Value Proposition

### 3.1 Ideal Customer Profile
1. **Regulated Fintech & Insurtech**: Teams governed by PCI-DSS, SOC 2 Type II, and GLBA who cannot send code off-premises.
2. **HealthTech & Life Sciences**: Organizations governed by HIPAA / FDA software validation rules with strict data boundaries.
3. **Enterprise B2B SaaS**: Companies with enterprise customer agreements mandating that customer IP and source code are never processed by external AI vendors.
4. **Defense, Intelligence & GovTech**: Organizations operating on isolated networks (AWS GovCloud, Azure Government, air-gapped on-premise clusters).

### 3.2 The Core Problem: The 60% "CI Friction Tax"
In a typical 150-engineer software organization:
- **Daily CI Runs**: 800–1,200 workflow executions.
- **Failure Rate**: 18–25% of pull request builds fail.
- **The Breakdown**:
  - **60% are mechanical / boring**: A developer updated a dependency in code but forgot the lockfile; an environment variable default was missing; a linter threw formatting errors; a test assertion drifted from string to integer.
  - **25% are flaky / infrastructure**: Cloud runner timeouts, socket blips, race conditions.
  - **15% are genuine logic regressions**: Actual product bugs requiring deep architectural context.
- **The Financial Cost**: 25 minutes lost per failure × 150 failed runs/day = **62.5 engineering hours wasted daily** on mundane CI triaging (~$1.8M annually).

### 3.3 The CIDRA Proposition: "The Zero-Leakage CI Janitor"
CIDRA does **not** try to be a Senior Software Architect. CIDRA is the **tireless CI Janitor**:
- It sweeps away the 60% mechanical failures automatically in under 45 seconds.
- It quenches flaky failures without burning LLM tokens.
- It steps aside and produces an actionable, structured diagnosis when real business logic is broken.
- It executes entirely within the customer's private perimeter.

---

## 4. Product Operational Boundaries & Failure-Class Coverage Matrix

### 4.1 The Operational Boundary Principle: Where CIDRA Automates vs Where CIDRA Stops
A critical design requirement for enterprise CI remediation is knowing **where to automate vs where to deliberately stop**. Generic coding bots attempt to fix every failure, resulting in corrupted production code, hidden race conditions, and catastrophic database loss.

CIDRA establishes a defensible, mathematically validated boundary:
- **Automated Janitor Scope**: Routine, deterministic, mechanical failures with single-point or bounded root causes are fully remediated in `< 45 seconds`.
- **Deliberate Refusal Scope**: Ambiguous, non-deterministic, high-blast-radius, or irreversible failure classes are **strictly refused (fail-closed)**. CIDRA emits structured Root Cause Analysis (RCA) receipts and routes to Human-in-the-Loop gates without modifying production code.

```
                                  CI Failure Detected
                                           │
            ┌──────────────────────────────┴──────────────────────────────┐
            ▼                                                             ▼
   Within Safe Janitor Scope                                 Outside Safe Janitor Scope
┌───────────────────────────────┐                             ┌───────────────────────────────┐
│ • Missing package/dependency  │                             │ • Flaky test (binomial flag)  │
│ • Unit test assertion drift   │                             │ • Database schema migrations  │
│ • Missing env var default     │                             │ • Core auth / security paths  │
│ • Upstream method deprecation │                             │ • CI runner timeouts/deadlock │
│ • Type / interface mismatch   │                             │ • Adversarial test tampering  │
│ • Formatting / lint failure   │                             │ • Blast-radius breach (>5 f.) │
└───────────────┬───────────────┘                             └───────────────┬───────────────┘
                │                                                             │
                ▼                                                             ▼
    [CIDRA Auto-Remediation]                                      [CIDRA Guardrailed Refusal]
   1. SBFL fault localization                                    1. Fail-closed: 0 fix attempts
   2. Zero-network sandbox patch                                 2. Emit structured RCA log
   3. Pre-execution AST audit gate                               3. Request Human-in-the-Loop review
   4. Re-run verification test suite                             4. No dirty branches or broken PRs
   5. Open auto-mergeable PR                                     5. Zero tokens burned on flakes
```

### 4.2 Comprehensive Failure-Class Coverage Matrix (14 Classes)

| Failure Class | Diagnose | Localize | Repair | Verify | Correct Refusal | Operational Boundary Action & Enterprise Rationale |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Dependency** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Adds missing package to manifest (`requirements.txt`, `pyproject.toml`) with pinned version constraint. |
| **Assertion** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: SBFL Ochiai isolates logic fault line. Fixes implementation without weakening test assertions. |
| **Config / Env** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Adds safe default fallback to configuration loader or `.env.example`. |
| **API Deprecation** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Migrates deprecated upstream call site (e.g. Pydantic v1 `dict()` $\rightarrow$ Pydantic v2 `model_dump()`). |
| **Type / Interface** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Adds null-safety guard (`Optional[T]`) or aligns function signature parameters. |
| **Multi-File Fault** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Coordinated patch across caller/callee components within 5-file containment limits. |
| **Build / Packaging** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Corrects PEP 517 build backend specification in `pyproject.toml` (e.g. `flit_core`, `setuptools`). |
| **Lint / Formatting** | ✓ | ✓ | ✓ | ✓ | — | **Auto-Remediate**: Applies deterministic code formatting or unused import cleanup (`ruff`, `flake8`). |
| **Flaky Test** | ✓ | — | `REFUSE` | ✓ | ✓ | **Strict Refusal**: Statistical binomial test detects non-determinism. Modifying code risks masking race conditions. Emits quarantine receipt with 0 tokens. |
| **Complex Migration** | ✓ | ? | `REFUSE` | ✓ | ✓ | **Strict Refusal / Gate**: Changes touching `migrations/**` or `**/*.sql` are blocked. Autonomous DDL alterations risk catastrophic, irreversible data loss. |
| **Core Auth / Sensitive** | ✓ | ✓ | `REFUSE` | ✓ | ✓ | **Human Approval Gate**: Changes touching `src/auth/**` or `payments/**` mandate explicit human signoff to prevent unauthorized privilege escalation. |
| **Timeout / Deadlock** | ✓ | ? | `REFUSE` | ✓ | ✓ | **Strict Refusal**: Asynchronous watchdog termination. Artificially bumping timeout values masks deadlocks without repairing root cause. |
| **Adversarial Cheating** | ✓ | ✓ | `REFUSE` | ✓ | ✓ | **Security Rejection**: Pre-execution AST gate intercepts test neutering (`assert True`, deleted tests, mock hijacking). 100% block rate. |
| **Blast-Radius Breach** | ✓ | ? | `REFUSE` | ✓ | ✓ | **Strict Refusal**: Diff exceeds containment limits (>5 files or >100 lines). Halts execution to prevent uncontrolled large-scale code rewrite. |

### 4.3 Why Deliberate Refusal Is a Core Enterprise Selling Feature
1. **Zero-Token Flaky Quenching**: Rather than repeatedly re-prompting an LLM on non-deterministic tests, CIDRA identifies intermittent failures using binomial probability ($k/5$ flips), freezes repair attempts, and opens an isolated quarantine issue.
2. **Data Loss Prevention in Migrations**: Enterprise databases cannot tolerate automated DDL scripts. CIDRA enforces a hard security boundary on `migrations/**` and `*.sql` files.
3. **Privilege Boundary Integrity**: Code within auth perimeters (`src/auth/**`, `payments/**`) cannot be modified without human cryptographic signoff.
4. **Guaranteed Zero False-Verified Rate**: Because AST gating intercepts test tampering *before* execution, CIDRA never marks a patch green by cheating.


---

## 5. Architectural Roadmap: The 5 Pillars of Enterprise CIDRA

```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CIDRA ENTERPRISE PLATFORM                                   │
├──────────────────────────────┬───────────────────────────────┬────────────────────────────────┤
│ 1. POLYGLOT FOUNDATION       │ 2. PRIVATE & AIR-GAPPED LLM   │ 3. DECLARATIVE POLICY ENGINE   │
│ • Python (pytest)            │ • Ollama / vLLM native engine │ • Path restriction rules       │
│ • TypeScript / Node (vitest) │ • Azure OpenAI VPC Endpoint   │ • Max diff & file boundaries   │
│ • Go (go test)               │ • --air-gapped strict mode    │ • Risk-tiered approval levels  │
├──────────────────────────────┼───────────────────────────────┼────────────────────────────────┤
│ 4. COMPLIANCE AUDIT RECEIPTS │ 5. ENTERPRISE PACKAGING       │                                │
│ • SHA-256 provenance hashes  │ • Self-Hosted GitHub Action   │                                │
│ • Verifiable network proof   │ • Air-gapped Docker Compose   │                                │
│ • SOC 2 / ISO 27001 evidence │ • Private Kubernetes Helm     │                                │
└──────────────────────────────┴───────────────────────────────┴────────────────────────────────┘
```

---

### Pillar 1: Polyglot Foundation (Node/TS & Go)

Enterprise repositories rarely run on Python alone. Expanding beyond Python is mandatory for enterprise adoption.

#### Architecture: Pluggable Language Adapter Interface
Define a standardized `LanguageAdapter` contract:

```python
class LanguageAdapter(ABC):
    @abstractmethod
    def parse_test_failures(self, raw_logs: str) -> list[FailureSignature]: ...
    
    @abstractmethod
    def localize_faults(self, repo_path: Path, failure: FailureSignature) -> list[FaultCandidate]: ...
    
    @abstractmethod
    def parse_ast(self, code: str) -> Any: ...
    
    @abstractmethod
    def audit_patch_ast(self, diff: str) -> AuditResult: ...
    
    @abstractmethod
    def apply_dependency_fix(self, manifest_path: Path, package: str, version: str | None) -> str: ...
```

#### Language Target Matrix

| Language | Test Framework | Fault Localization Strategy | Manifest & Lockfile | AST Security Engine |
| :--- | :--- | :--- | :--- | :--- |
| **Python** *(Existing)* | `pytest` | `pytest-cov` + Ochiai / Tarantula matrix | `pyproject.toml`, `requirements.txt` | Python native `ast` module |
| **TypeScript / Node** | `vitest`, `jest` | V8 Coverage JSON (`c8`) + SBFL spectrum parser | `package.json`, `pnpm-lock.yaml`, `package-lock.json` | Tree-sitter / Babel AST parser (blocking `eval`, `child_process`, `net.connect`) |
| **Go** | `go test` | `go test -coverprofile` + statement coverage matrix | `go.mod`, `go.sum` | Native Go `go/parser` / Tree-sitter (blocking `os/exec`, `net`, `unsafe`) |

---

### Pillar 2: First-Class On-Premises & Air-Gapped LLM Integration

#### Enterprise Problem
Security-conscious organizations explicitly block outbound internet traffic from their CI runners. Public APIs (OpenAI, Anthropic, OpenRouter) fail at the network gateway level.

#### The Solution: Native Local Engine Driver
CIDRA will ship with built-in connection presets for local inference engines running on the internal corporate network:

1. **Ollama Driver**: Direct local HTTP binding (`http://localhost:11434` or internal cluster DNS).
2. **vLLM / TGI Driver**: High-throughput self-hosted inference server with OpenAI-compatible API (`http://vllm.internal.corp:8000/v1`).
3. **Azure OpenAI Private Endpoint Driver**: Authenticates via Azure Managed Identity / Service Principal across private VPC peering without traversing the public internet.
4. **AWS Bedrock VPC Driver**: Routes inference requests through AWS PrivateLink endpoints.

#### Recommended Self-Hosted Models for Code Repair
- **Tier 1 (High Performance)**: `Qwen2.5-Coder-32B-Instruct`, `DeepSeek-Coder-V2-Lite-16B`
- **Tier 2 (Resource Constrained / CPU)**: `Qwen2.5-Coder-7B-Instruct`, `Llama-3.1-8B-Instruct`

#### The `--air-gapped` Certified Mode
When enabled via CLI (`cidra fix --air-gapped`) or environment (`CIDRA_AIR_GAPPED=true`):
- All external HTTP telemetry is hard-disabled.
- Base URLs must resolve to private/local IP addresses (`127.0.0.1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Public IPs are blocked.
- Any attempt to resolve public DNS names throws an immediate fail-stop error.

---

### Pillar 3: Declarative Security Policy Engine (`cidra.policy.yml`)

#### Enterprise Problem
SecOps teams will not permit an autonomous bot to make unrestricted edits across a repository. There must be an immutable, code-defined contract specifying what files can be touched and what fix types are authorized.

#### Specification: `cidra.policy.yml`
Repositories define their safety policy in the repository root:

```yaml
version: "1.0"
metadata:
  repository: "enterprise/core-ledger"
  classification: "restricted"

# Strict boundaries on allowable automatic fixes
remediation_policy:
  auto_pr_enabled: true
  allowed_categories:
    - missing_dependency
    - missing_env_variable
    - test_assertion_drift
    - linter_formatting
  
  escalate_to_human_only:
    - business_logic_regression
    - multi_file_dependency_conflict
    - performance_timeout

# Zero-touch zones: CIDRA will fail-stop if a proposed diff touches any matching path
forbidden_paths:
  - "src/auth/**"
  - "src/payments/**"
  - "migrations/**"
  - ".github/workflows/**"
  - "security/**"
  - "**/*.pem"
  - "**/*.key"

# Blast-radius containment rules
containment_limits:
  max_files_changed: 2
  max_diff_lines: 25
  allow_new_file_creation: false
  allow_file_deletion: false

# Execution sandbox enforcement
sandbox_profile:
  engine: "docker"
  timeout_seconds: 45
  memory_limit_mb: 2048
  cpu_quota: 2.0
  network_egress: "strictly_denied"
  pids_limit: 100
```

#### Enforcement Lifecycle in LangGraph
The Policy Engine evaluates candidate patches at two distinct checkpoints:
1. **Pre-Execution Check**: Verifies that the localized faulty lines do not intersect with `forbidden_paths`.
2. **Post-Patch Check**: Inspects the generated `git diff` against `max_files_changed`, `max_diff_lines`, and path filters before passing to the AST Security Gate.

---

### Pillar 4: Cryptographic Compliance Audit Receipts

#### Enterprise Problem
During annual SOC 2 Type II or ISO 27001 audits, compliance teams must prove that automated tooling running in production pipelines did not introduce unvetted vulnerabilities, leak intellectual property, or bypass change management controls.

#### The Solution: Signed Run Manifest (`cidra_audit_manifest.json`)
Every intervention generates an immutable, cryptographically verifiable artifact:

```json
{
  "$schema": "https://cidra.dev/schemas/v1/audit-manifest.json",
  "audit_version": "1.0.0",
  "timestamp": "2026-09-29T08:15:00Z",
  "run_id": "run_01j8x9a2k4bc7d1",
  "provenance": {
    "repository": "enterprise/core-ledger",
    "commit_sha": "a1b2c3d4e5f67890abcdef1234567890abcdef12",
    "initiator": "ci_pipeline_webhook",
    "cidra_engine_version": "2.0.0"
  },
  "security_evaluation": {
    "policy_file_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
    "forbidden_paths_checked": true,
    "ast_audit_verdict": "PASSED",
    "ast_blocked_calls_detected": [],
    "sandbox_network_egress_bytes": 0,
    "sandbox_container_id": "c71a9e8b012d"
  },
  "localization": {
    "algorithm": "Ochiai-SBFL",
    "suspiciousness_score": 0.894,
    "targeted_file": "src/ledger/calculator.py",
    "targeted_lines": [42]
  },
  "remediation": {
    "category": "missing_dependency",
    "fix_strategy": "append_requirement",
    "diff_sha256": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "verification_test_exit_code": 0,
    "verification_stdout_summary": "14 tests passed in 1.42s"
  },
  "compliance_signature": {
    "signer": "cidra-agent-local-key",
    "signature": "MEQCIG9X...Z0A1="
  }
}
```

---

### Pillar 5: Self-Hosted Enterprise Delivery Vehicles

To be adopted by corporate IT and platform teams, CIDRA must fit standard deployment topologies:

```
                  ENTERPRISE DEPLOYMENT TOPOLOGIES
                  
Topologies:
1. Ephemeral Self-Hosted Action       2. Dedicated VPC Daemon
┌───────────────────────────────┐     ┌───────────────────────────────────────────┐
│ GitHub Actions Runner (Host)  │     │ Private VPC / Kubernetes Cluster          │
│ ┌───────────────────────────┐ │     │ ┌───────────────────────────────────────┐ │
│ │ CIDRA Ephemeral Runner    │ │     │ │ CIDRA Service (Daemon / Helm Chart)   │ │
│ │ (Container action)        │ │     │ │ • Webhook Listener (GitHub / GitLab)  │ │
│ └─────────────┬─────────────┘ │     │ │ • Local Worker Pool                   │ │
│               ▼               │     │ │ • Embedded Dashboard & SQLite         │ │
│ ┌───────────────────────────┐ │     │ └───────────────────┬───────────────────┘ │
│ │ Zero-Network Sandbox Cont.│ │     │                     ▼                     │
│ └───────────────────────────┘ │     │ ┌───────────────────────────────────────┐ │
│ Runs inside corporate VPC     │     │ │ Internal LLM Cluster (vLLM / Ollama)  │ │
└───────────────────────────────┘     │ └───────────────────────────────────────┘ │
                                      └───────────────────────────────────────────┘
```

#### Delivery Format A: GitHub Action for Self-Hosted Runners
A zero-dependency GitHub Action that runs directly inside enterprise-managed runners:
```yaml
- name: Autonomous CI Remediation
  uses: enterprise-actions/cidra@v2
  if: failure()
  with:
    policy-file: ".github/cidra.policy.yml"
    llm-endpoint: "http://internal-vllm.corp.local:8000/v1"
    air-gapped: "true"
    github-token: ${{ secrets.INTERNAL_PAT }}
```

#### Delivery Format B: Kubernetes Helm Chart (`cidra-operator`)
For enterprise platforms orchestrating multi-repo microservices:
- Deploys a stateless webhook listener receiver for GitHub Enterprise / GitLab self-managed events.
- Spawns isolated job runners inside a restricted Kubernetes namespace with `NetworkPolicy` blocking all egress except internal LLM DNS.

---

## 6. Implementation Phases & Milestones

```
Timeline: 10-Week Enterprise Transformation
┌─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┐
│ Weeks 1-2               │ Weeks 3-4               │ Weeks 5-7               │ Weeks 8-10              │
│ Security Policy &       │ Compliance Receipts &   │ Polyglot Foundation     │ Packaging & Helm        │
│ Air-Gapped Mode         │ On-Prem LLM Suite       │ (Node/TS & Go)          │ Distribution            │
└─────────────────────────┴─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

### Phase 1: Security Policy Engine & Air-Gapped Core (Weeks 1–2)
- [ ] Implement `cidra.policy.yml` schema validator and parser using Pydantic.
- [ ] Add path restriction validation before and after fix generation.
- [ ] Implement the `--air-gapped` CLI and runtime flag enforcing zero public DNS resolution.
- [ ] Unit & integration tests for policy violations and fail-closed behaviors.

### Phase 2: Audit Receipts & On-Prem LLM Drivers (Weeks 3–4)
- [ ] Build `AuditManifestGenerator` producing the cryptographically signed `cidra_audit_manifest.json`.
- [ ] Implement native connection presets for Ollama, vLLM, and Azure OpenAI VPC endpoints.
- [ ] Add prompt safety sanitization ensuring internal secrets/tokens in logs are scrubbed prior to reaching local LLMs.

### Phase 3: Polyglot Support (TypeScript/Node & Go) (Weeks 5–7)
- [ ] Build `NodeAdapter` supporting `vitest` / `jest` failure parsing, coverage mapping, and `package.json` updating.
- [ ] Implement TypeScript AST security checker using tree-sitter.
- [ ] Build `GoAdapter` supporting `go test -coverprofile` and `go.mod` dependency updates.
- [ ] Create polyglot test fixtures validating zero-network sandbox isolation across languages.

### Phase 4: Enterprise Packaging & Operator Deployment (Weeks 8–10)
- [ ] Publish official GitHub Action container image with pre-baked language runtimes.
- [ ] Author standard `docker-compose.yml` for turnkey single-machine VPC deployment.
- [ ] Develop Kubernetes Helm chart with restricted `SecurityContext` and `NetworkPolicy` definitions.
- [ ] Author enterprise administrator documentation and SOC 2 compliance mapping guide.

---

## 7. Success Metrics & Key Performance Indicators (KPIs)

To evaluate product effectiveness in an enterprise deployment, CIDRA measures four non-negotiable metrics:

| Metric | Target | Rationale |
| :--- | :--- | :--- |
| **False-Positive Repair Rate** | **< 0.5%** | An automated bot that breaks code will be uninstalled within 48 hours. CIDRA must prefer refusing a fix over submitting an unverified diff. |
| **Verification Accuracy** | **100.0%** | Zero patches may ever be submitted as a pull request unless verified completely green inside the isolated sandbox. |
| **Mean Time to Remediate (MTTR)** | **< 45 seconds** | Mechanical failures must be resolved faster than a human developer can switch contexts and read the log. |
| **Audit Compliance Rate** | **100.0%** | Every single intervention must produce a validated, non-repudiable audit manifest. |

---

## 8. Summary: Why This Wins

By shifting from "another AI tool that wants your GitHub token" to **"the self-hosted, guardrailed CI remediation engine for privacy-sensitive enterprises"**, CIDRA solves an acute, expensive problem with clear unit economics, zero security compromises, and a defensible engineering moat.
