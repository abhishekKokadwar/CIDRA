# CIDRA Verification, Validation & Distribution Plan

## 1. Addressing the Deployment Dilemma
You raised a very valid point: *a CI agent running locally doesn't seem to make sense, but cloud hosting is too expensive.* 

Here are the three best ways to distribute CIDRA via PyPI/npm without needing AWS/Cloud hosting, making it incredibly useful to other developers:

### Approach A: The Local CLI Dev Tool (Highly Recommended for PyPI)
Instead of waiting for CI to fail, CIDRA becomes a local debugging assistant.
- **How it works:** A developer installs it via `pip install cidra`. When their local tests fail, they run `cidra fix`.
- **Why it makes sense locally:** It immediately spins up the local Docker sandbox, reproduces the failure without messing up their host environment, queries the LLM (using their local API key), and generates a git patch or branch locally. It brings the power of an autonomous agent to the local dev loop.

### Approach B: The GitHub Actions Native Action (Zero-Cost CI)
Instead of hosting a webhook server, package CIDRA to run *inside* the user's GitHub Actions runner.
- **How it works:** Users add `uses: your-name/cidra-action@v1` to their `.github/workflows/ci.yml`. When a test fails, the GitHub Action itself runs your Python engine.
- **Why it makes sense:** GitHub provides the compute for free. The Action uses Docker-in-Docker to run the sandbox, does the analysis, and posts the PR. Zero AWS costs for you or the user.

### Approach C: The "Self-Hosted" Webhook Server
- **How it works:** Users `pip install cidra-server`, then run `cidra serve --tunnel`. You integrate `ngrok` or Cloudflare Tunnels natively into the CLI.
- **Why it makes sense:** The user runs it on an old laptop, Raspberry Pi, or local server. It exposes a webhook URL to GitHub, acting as a real CI bot, but using the user's own electricity and API keys (BYOK).

---

## 2. Phase-by-Phase Verification & Validation Plan

To validate the code you have already built using the `cidra_practice` repository, we will follow a strict, isolated testing plan.

### Preparation Phase
1. **Set up `cidra_practice` locally:** Ensure we have the practice repo cloned or accessible.
2. **Environment Variables:** Configure the `CIDRA_API_KEY` (using Gemini or another LLM) and a GitHub PAT (Personal Access Token) for read/write.
3. **Docker Check:** Ensure the local Docker daemon is running and the `cidra-sandbox:base` image is built.

### Verification Steps (Mapping to `phases.md`)

#### Phase 1-3: Ingestion, Isolation & LLM Analysis
*Goal: Prove the engine can find the error in a raw log and diagnose it correctly without running code.*
- **Action:** Feed the saved `raw.log` files from the 7 fixtures in `cidra_practice` into the `fetch_log` and `analyze` nodes.
- **Validation:** 
  - Ensure the isolated error region contains the actual `Traceback` or `Error`.
  - Validate the LLM outputs structured JSON.
  - Verify the `category` matches the expected ground truth for each fixture.

#### Phase 4: Docker Sandbox Hardening
*Goal: Prove the sandbox reproduces failures safely.*
- **Action:** Run the sandbox against the `cidra_practice` intentionally broken commits.
- **Validation:**
  - The sandbox must reproduce the exact red error state.
  - Run adversarial tests (e.g., trying to access network or Docker socket from within the test code) and ensure they are blocked.
  - Verify container cleanup (no orphaned containers left behind).

#### Phase 5: The Fix + Verify Loop
*Goal: Prove the agent can fix code and verify it green.*
- **Action:** Run the full loop on rank 1 and rank 2 fixtures (e.g., missing dependency, simple assertion).
- **Validation:**
  - The agent generates a fix diff.
  - The patch is applied inside the sandbox.
  - The re-run goes **green**.
  - Flaky tests (like F-04) are flagged as `flaky_detected` and NOT fixed.

#### Phase 6 & 9: Git Operations & PR Scaffolding
*Goal: Prove the agent can safely isolate code and create a PR.*
- **Action:** Trigger a successful fix generation and let it proceed to PR creation.
- **Validation:**
  - The `git-worktree` checkouts work without `.git` leaking into the sandbox.
  - A draft PR is successfully posted to `cidra_practice` using the GitHub REST API.
  - No system-level git configs are altered (hardened git wrapper check).

#### Phase 10: Static Policy Checks (Audit)
*Goal: Prove the agent cannot cheat.*
- **Action:** Feed the agent a malicious diff that deletes a test assertion to force a pass.
- **Validation:** The `audit_patch` node must reject the diff before it even reaches the sandbox.

### 3. Next Steps for Us
To execute this plan, we should:
1. **Pick the distribution model** (CLI, GitHub Action, or Self-hosted webhook) so we can tailor the final entrypoint.
2. **Start executing the verification.** Do you want me to write the validation scripts to run against `cidra_practice`, or should we start testing Phase 2/3 manually right now?
