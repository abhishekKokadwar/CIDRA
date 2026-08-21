# Project Understanding Doc — CIDRA (Continuous Integration Debugging and Repair Agent)

> Read this once fully before you write a single line of code. The goal is that by the
> end you can explain the whole system on a whiteboard and you know where the landmines are.

---

## 1. What this project actually is (in plain words)

A bot that wakes up when someone's CI build fails, reads the (huge, noisy) build log so a
human doesn't have to, figures out *what* broke and *why*, tries to reproduce the failure
in a throwaway Docker container, and then leaves a useful artifact behind — ideally a Pull
Request with a fix, at minimum a clear comment saying "here's the root cause and here's a
suggested fix."

The whole thing is an **agent**: an LLM that runs in a loop, calls tools (read log, run
shell command in sandbox, edit file, open PR), looks at the results, and decides the next
step. LangGraph is just the framework that makes that loop a clean, debuggable **state
machine** instead of a tangle of `if` statements.

### The mental model

```
CI fails  ──webhook──▶  Agent wakes up
                          │
                          ▼
            ┌─────────────────────────────┐
            │  Log Ingestion               │  pull raw log, isolate the error region
            ├─────────────────────────────┤
            │  Root-Cause Analysis (LLM)   │  "missing dep? race? assertion?"
            ├─────────────────────────────┤
            │  Reproduction (Docker)       │  check out commit, run failing test
            ├─────────────────────────────┤
            │  Fix + Verify (Docker)       │  edit, re-run test in sandbox
            ├─────────────────────────────┤
            │  Output (GitHub API)         │  open PR / post comment
            └─────────────────────────────┘
```

Each box is a **node** in LangGraph. The arrows are **edges**. Some edges are conditional
("if reproduction failed, go back and re-analyze" / "if you've retried 3 times, give up and
just post the analysis").

---

## 2. The single most important decision: scope

Read this section twice. It will save your project.

The literal spec — *"generates a PR with the fix"* for any failing build — is **automated
program repair**, an unsolved research problem. You will not build a reliable version of
that in ~25–30 hours, and neither will anyone else. If you aim at the literal spec you will
end up with something that works in a demo video once and never again, which is *worse* for
your resume than a smaller thing that works every time.

**So you scope by failure class, not by ambition.** Pick a small set of failure types your
agent handles *reliably*, and design the architecture so more types could be plugged in later.

Good starter failure classes (pick 2–3):

| Failure class | Why it's tractable |
|---|---|
| Missing dependency (`ModuleNotFoundError`, `ImportError`) | Fix = add to requirements; easy to detect, easy to verify |
| A genuinely flaky test (passes on re-run) | Fix = detect non-determinism, re-run N times, quarantine/flag; no real "fix" needed |
| Simple assertion / off-by-one in test or fixture | LLM can often patch it; verifiable by re-running |
| Wrong env var / config missing in CI | Detectable from log, fixable in workflow file |

What you explicitly **do not** claim: "fixes any bug." Your README and your resume bullet
say it **diagnoses failures and proposes verified fixes for a class of common CI failures**,
with an extensible architecture. That sentence is both true and impressive.

### MVP vs stretch

**MVP (the thing you must finish):**
1. Webhook receiver that fires on a failed CI run.
2. Log ingestion + smart isolation of the error region.
3. LLM root-cause analysis that outputs structured JSON (`category`, `file`, `line`, `reason`).
4. Docker sandbox that checks out the commit and reproduces the failure.
5. For your chosen failure classes: apply a fix, re-run in the sandbox, confirm green.
6. Output: post a comment (and/or open a PR) with the diagnosis + diff.

**Stretch (only if you have spare days):**
- Vector-RAG over the log instead of regex isolation (see §6 — often unnecessary).
- Handle multiple failure classes.
- A small web dashboard showing run history.
- GitLab support in addition to GitHub.

If you're running out of time, cut in this order: stretch items → PR creation (downgrade to
"post a comment with the diff") → fix-and-verify (downgrade to "diagnose + suggest"). Even
the fully downgraded version (webhook → ingest → diagnose → reproduce → comment) is a solid
project.

---

## 3. The components, one by one

### 3.1 The webhook receiver

CI providers can POST to a URL when an event happens (a run completes/fails). You need a
small web server (FastAPI is ideal) with one endpoint that:
- **Verifies the signature.** GitHub signs the payload with a secret (`X-Hub-Signature-256`,
  HMAC-SHA256). If you don't verify it, anyone can trigger your agent. This is the #1 thing
  juniors skip and seniors notice.
- **Responds fast (within a few seconds), then does work in the background.** Webhook
  senders time out and retry. If your endpoint runs a 4-minute Docker job inline, GitHub
  will think it failed and resend → you'll process the same failure 3 times. Return `200`
  immediately, push the job to a background task/queue.
- **Is idempotent.** Because of retries, design so processing the same `run_id` twice is
  harmless (check "have I already handled this run?").

For local dev you can't receive a public webhook on `localhost`, so you use a tunnel
(`ngrok`, `cloudflared`) or you skip the live webhook entirely during development and feed
saved JSON payloads into the handler directly. Do the latter first; wire up the real webhook
last.

### 3.2 Log ingestion + isolation

The raw log can be 10k+ lines, 95% of it noise (dependency install spam, progress bars,
timestamps). Feeding all of it to the LLM is expensive and *worse* for quality — the model
gets distracted. Your job is to hand the LLM the ~50–200 relevant lines.

Strategy, cheapest-first:
1. **Strip noise** — ANSI color codes, carriage-return progress bars, timestamps.
2. **Anchor on error markers** — search for `Traceback`, `Error`, `FAILED`, `assert`,
   `Exception`, `npm ERR!`, exit codes. Grab a window around each hit (e.g. 30 lines before,
   60 after).
3. **Only if that isn't enough** reach for embeddings/RAG (see §6).

This "smart retrieval" step is the technical heart of the log side. Don't over-engineer it.

### 3.3 Root-cause analysis (the LLM node)

You give the LLM the isolated error region plus minimal repo context and ask for
**structured output** — make it return JSON, not prose:

```json
{
  "category": "missing_dependency",
  "confidence": 0.9,
  "file": "requirements.txt",
  "evidence": "ModuleNotFoundError: No module named 'requests'",
  "proposed_action": "add 'requests' to requirements.txt"
}
```

Structured output is what lets the rest of your graph *route*. The `category` field decides
which fix strategy runs next. Prose can't drive a state machine; JSON can.

Use a JSON-mode / structured-output feature of whatever model API you use, and **validate**
the result (Pydantic). LLMs occasionally return malformed JSON — handle it, don't crash.

### 3.4 The Docker sandbox (the scary one)

This is where the project earns its "advanced" label and where most of your risk lives.

What it does: spin up a container, check out the failing commit inside it, install deps,
run the failing test, capture the result. Later, apply a candidate fix and re-run.

**Why a sandbox at all:** you're about to run untrusted code (the repo's test suite) and,
worse, code the LLM wrote. You do *not* run that on your host machine. The container is the
blast radius.

Hard rules (these are also great interview talking points):
- **No `--privileged`. No mounting the Docker socket into the container.** Giving a container
  the Docker socket = giving it root on your host. The LLM should never get near it.
- **Network off by default** (`network_mode="none"`) unless a step truly needs to install
  deps. Untrusted code with internet is how you get a crypto miner.
- **Resource limits**: cap memory, CPU, and PIDs so a fork-bomb or memory leak can't take
  down your machine.
- **Timeouts on everything.** A hung test must be killed. Wrap every container exec in a
  timeout.
- **Always clean up.** Use try/finally (or `--rm`) so containers and volumes don't pile up.
- **Treat the LLM's shell commands as hostile input**, even though *you* wrote the prompt.
  Don't `eval` its output on the host; only ever run it *inside* the container.

You'll talk to Docker from Python via the **Docker SDK** (`docker` package). Build a base
image once with the common toolchain so each run is fast; do the per-run checkout/test
inside a container from that image.

### 3.5 Fix + verify loop

For your chosen failure class: generate a candidate change, apply it *inside the sandbox*,
re-run the failing test. Green → you have a verified fix. Still red → either retry with the
new error as feedback (bounded retries!) or give up gracefully and downgrade to "diagnosis
only."

The **verification** is the credible part. "The agent guessed a fix" is weak; "the agent
*proved* the fix turns the build green in an isolated reproduction" is strong. Lead with that.

### 3.6 Output (GitHub API)

Two levels:
- **Comment** (easy): post the diagnosis + suggested diff as a comment on the commit/PR.
- **Pull Request** (nicer): create a branch, commit the fix, open a PR. The GitHub API
  (`PyGithub` or REST) does this; you authenticate as a GitHub App or with a fine-scoped
  token.

Start with the comment. Add the PR if time allows.

---

## 4. LangGraph: what you actually need to understand

Don't get lost in LangGraph's full feature set. The 20% you need:

- **State** — a single typed object (a `TypedDict` or Pydantic model) that flows through the
  graph. Every node reads from it and returns updates to it. Put everything here: raw log,
  isolated error, the analysis JSON, the sandbox result, retry count.
- **Nodes** — plain Python functions: `state in → partial state out`. Your nodes are
  `ingest_log`, `analyze`, `reproduce`, `fix`, `verify`, `publish`.
- **Edges** — wiring between nodes. Most are fixed ("after analyze, go to reproduce").
- **Conditional edges** — a function that looks at state and picks the next node. This is how
  you express "if not reproduced, retry; if retries ≥ 3, go to publish-as-diagnosis-only."
- **Why bother vs a `while` loop:** state is explicit and inspectable, the graph is
  visualizable, retries/branches are declarative, and you can checkpoint/resume. Those are
  exactly the things that make it sound senior in an interview. You're using a state machine
  because agent control flow is messy and you want it legible.

Build a trivial 3-node graph on day one (see prep doc) so the API stops being abstract.

---

## 5. The data flow / state object (sketch this on paper)

```python
class DebugState(TypedDict):
    run_id: str
    repo: str
    commit_sha: str
    raw_log: str
    error_region: str          # output of ingestion
    analysis: dict | None      # structured root-cause JSON
    reproduced: bool
    fix_diff: str | None
    verified: bool
    retries: int
    final_output: str          # comment body / PR url
```

If you can fill this struct out and explain how each field gets populated and which node
reads it, you understand the project.

---

## 6. Minute things / gotchas you must know *before* starting

These are the things that quietly eat days.

**On RAG over logs (read this — it changes your plan):**
- "You need RAG for the logs" is the part of the brief I'd push back on. Logs are *not* like a
  knowledge base. The relevant lines are usually findable by **regex/heuristics** (search for
  `Traceback`, error keywords, the failing test name). That's faster, cheaper, deterministic,
  and easier to demo than embeddings.
- Vector-RAG earns its place only when you can't anchor on keywords — e.g. semantic search
  across *many historical* failures ("have we seen this error before?"). That's a legit
  stretch feature.
- Practical recommendation: build keyword/heuristic isolation for the MVP. If you want the
  RAG resume bullet, add a small vector layer for "find similar past failures" as a stretch,
  using **Chroma** (embedded, zero infra) — not a full Qdrant/Pinecone deployment you have to
  host. Chunk logs with simple **fixed-size chunking with overlap** (logs are unstructured;
  semantic chunking buys you little here).

**Security / sandbox:**
- Never mount the Docker socket into a container. Never `--privileged`. This is the single
  biggest "junior mistake" in code-execution projects.
- Default network off; only enable for the explicit dependency-install step.
- Set memory, CPU, PID, and time limits on every container.
- The LLM's output is untrusted even though you prompted it. Run it only inside the sandbox.

**Webhooks:**
- Verify the HMAC signature — non-negotiable.
- Return 200 immediately, process async, or you'll get duplicate retries.
- Make processing idempotent on `run_id`.
- You can't receive webhooks on localhost — use ngrok, or (better for dev) replay saved
  payloads and wire the live webhook last.

**LLM specifics:**
- Force **structured JSON output** and validate with Pydantic; handle malformed responses.
- **Bound every loop.** Agents that retry forever burn money and time. Hard cap retries (e.g. 3).
- **Cost control.** Each run can be several LLM calls × large context. Trim context
  aggressively (that's what §3.2 is for). Test against *saved* logs, not live runs, while
  developing — it's free and instant.
- Don't paste secrets (repo tokens, API keys) into prompts.

**GitHub API:**
- Use a **fine-grained token** scoped to one test repo with only the permissions you need
  (contents, pull requests). Never a full-access classic token.
- Rate limits exist; you won't hit them at this scale, but know they're there.
- For a clean demo, create a dedicated **practice repo** with intentionally broken commits
  (one per failure class). Don't test on anything real.

**General engineering:**
- Everything reproducible failure-first: keep a folder of *saved* failing logs + the commits
  that produced them. Your whole dev loop should run offline against these. Live webhook +
  live CI is the last 10%, not the first.
- Idempotency, timeouts, and cleanup are the difference between "demo" and "I'd actually
  trust this."

---

## 7. What "done" looks like (acceptance checklist)

- [ ] A saved failing log can be fed in and the agent isolates the correct error region.
- [ ] The analysis node returns valid structured JSON with a correct `category`.
- [ ] The sandbox checks out the commit and *reproduces* the failure (goes red).
- [ ] For each chosen failure class, the agent applies a fix and the sandbox goes *green*.
- [ ] The agent posts a comment (and/or PR) with the root cause + the verified diff.
- [ ] All loops are bounded; containers are always cleaned up; webhook signature is verified.
- [ ] README clearly states the *scoped* claim, the architecture diagram, and a demo GIF.

If those are ticked, you have a project that's honest, demoable every time, and genuinely
impressive to talk about.

---

## 8. The resume bullet (write it now, build toward it)

> Built an autonomous CI failure-triage agent (Python, LangGraph, Docker SDK, GitHub API)
> that ingests build logs, isolates root cause via smart log retrieval, reproduces failures
> in a network-isolated, resource-capped Docker sandbox, and opens PRs with fixes verified
> green before suggesting them — handling common failure classes with an extensible
> node-based architecture.

Every clause in that sentence maps to a component above, and every clause is something you
can defend in an interview. Build until the sentence is true.
