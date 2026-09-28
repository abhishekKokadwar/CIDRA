# API Contracts — CIDRA Webhook (Phase 7)

> The live trigger surface. A GitHub Actions failure reaches CIDRA as a signed
> `workflow_run` webhook; CIDRA verifies it, dedupes it, and runs the engine in
> the background. Everything downstream (log fetch, sandbox, comment) is the
> Phases 0–6 engine unchanged — this doc covers only the boundary.
>
> Implementation: [`cidra/server/`](../cidra/server/). Security rationale:
> [4_architecture.md](4_architecture.md) §2 (zones), [threat/](threat/) (SR-06/08).

---

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Health check → `{"service":"cidra","ok":true}` |
| `POST` | `/webhook` | GitHub `workflow_run` deliveries |

## 2. `POST /webhook` — request

Sent by GitHub. Relevant headers:

| Header | Meaning |
|---|---|
| `X-Hub-Signature-256` | `sha256=<hmac>` of the raw body under the shared secret |
| `X-GitHub-Event` | event type; CIDRA acts only on `workflow_run` |
| `X-GitHub-Delivery` | GitHub's delivery UUID (retries reuse the event, not this id) |

Body: the GitHub `workflow_run` event JSON. CIDRA reads only these fields:

```jsonc
{
  "action": "completed",                       // must be "completed"
  "repository": { "full_name": "owner/name" },
  "workflow_run": {
    "id": 123456789,                           // → run_id
    "head_sha": "abc123…",                     // → commit_sha, PR-by-SHA lookup
    "conclusion": "failure",                   // must be "failure"
    "pull_requests": [ { "number": 42 } ]      // → issue_number (may be empty)
  }
}
```

## 3. `POST /webhook` — responses

| Status | When | Body |
|---|---|---|
| `401` | signature missing/invalid | `invalid signature` |
| `400` | signature valid but body isn't JSON | `invalid json` |
| `204` | valid, but not an actionable failure (success, wrong event, in-progress) | — |
| `200` | accepted — newly claimed, engine dispatched | `accepted` |
| `200` | duplicate delivery — already claimed | `duplicate: no-op` |

**Handler order is the contract** (see [`app.py`](../cidra/server/app.py)) and must not be
reordered: **verify → parse → claim → 200 → dispatch**. Verification precedes any parsing, so an
unauthenticated request never reaches the JSON decoder — proven by
`test_webhook_app.py::test_signature_checked_before_parse`.

## 4. Verification

HMAC-SHA256 over the **raw** request bytes under `CIDRA_WEBHOOK_SECRET`, constant-time compared
([`security.py`](../cidra/server/security.py)). Computing over re-serialized JSON would change the
bytes and always mismatch — the raw body is used. Fails closed: no secret, no header, or any
mismatch → 401.

## 5. Idempotency

Key: `(run_id, commit_sha)`, in SQLite ([`idempotency.py`](../cidra/server/idempotency.py)). The
key is **claimed before dispatch**, so a duplicate delivery returns `200 duplicate: no-op` and the
engine runs exactly once. A run claimed but not completed (mid-run crash) stays claimed — a retry
of that same delivery is a no-op, so recovery is by a fresh run, not a retry. SQLite persists the
claim across a restart, which is when GitHub's retry is most likely to land.

## 6. PR resolution

`issue_number` decides where the comment goes:

1. `workflow_run.pull_requests[0].number` if present (same-repo runs).
2. Else look up the PR by `head_sha` via the **read-only** client (fork PRs leave the array
   empty) — [`events.resolve_issue_number`](../cidra/server/events.py).
3. Else `None` → the publish node **dry-runs** (renders, does not post). Safe default, never a crash.

The lookup uses the read-only token by design (SR-06): the path that reacts to an untrusted
payload must not hold the write token.

## 7. Background execution

FastAPI `BackgroundTasks`, in-process: the 200 returns before the engine runs, so GitHub's ~10s
delivery timeout is never hit by a multi-minute sandbox run. A durable queue is deferred to
Phase 13; until then idempotency + GitHub retries cover a lost background run. A background
exception is logged and swallowed ([`worker.py`](../cidra/server/worker.py)) — it can't 500 a
request that already returned.

## 8. BYOK & secrets

CIDRA is Bring-Your-Own-Key: `CIDRA_API_KEY` + `CIDRA_BASE_URL` (any OpenAI-compatible endpoint)
and the two GitHub PATs come from the environment, never committed or stored. The webhook process
is **Zone 4** — it holds the keys. The sandbox container is **Zone 3** — no key ever enters it
(SR-08). These are separate processes; the boundary is enforced by the runner, not by trust.

## 9. Local setup

```bash
export CIDRA_WEBHOOK_SECRET="$(openssl rand -hex 20)"   # + the BYOK vars from .env
uvicorn cidra.server.app:app --port 8000
ngrok http 8000                                          # public URL for GitHub
```

Then register a webhook on the repo (Settings → Webhooks):

- **Payload URL:** `https://<ngrok>/webhook`
- **Content type:** `application/json`
- **Secret:** the same `CIDRA_WEBHOOK_SECRET`
- **Events:** *Workflow runs* only

A failing run then triggers CIDRA with no manual command. Verify with GitHub's
"Recent Deliveries" (200 = accepted) and the comment on the PR.

## 10. Local replay (no tunnel)

`scripts/replay_delivery.py` drives the whole pipeline — real HMAC, real graph, real Docker
sandbox, real comment — without a public URL. It sends exactly what GitHub sends (same raw body,
same `workflow_run` headers, signed with `CIDRA_WEBHOOK_SECRET`); the only thing it does not prove
is that GitHub's own POST reached the box, which is pure transport. Needs Docker up and the write
token set (BYOK, §8).

```bash
# terminal 1 — the server
export CIDRA_WEBHOOK_SECRET=devsecret   # + BYOK vars & write token in .env
uvicorn cidra.server.app:app --port 8000

# terminal 2 — replay a REAL failed run (fetches its head_sha + PR via the RO token)
export CIDRA_WEBHOOK_SECRET=devsecret
python scripts/replay_delivery.py --repo helpmecode69/cidra-practice --run-id <RUN_ID>

# prove idempotency in one shot: accepted, then 200 "duplicate: no-op"
python scripts/replay_delivery.py --repo helpmecode69/cidra-practice --run-id <RUN_ID> --twice
```

`--sample --sha <SHA>` builds a canned payload with no GitHub call, useful to smoke-test the
receiver alone (downstream log fetch won't find a real run). Get a `<RUN_ID>` from a failed run:
`gh run list -R helpmecode69/cidra-practice --status failure`.
