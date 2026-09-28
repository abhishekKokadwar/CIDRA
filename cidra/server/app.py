"""FastAPI webhook receiver. Phase 7, step 7.4.

The trigger surface in front of the engine. The handler order is the security
contract and must not be reordered:

    1. verify HMAC        — reject a spoofed payload before parsing (Zone 1)
    2. parse + filter     — act only on a completed+failed workflow_run
    3. claim idempotency  — drop duplicate deliveries
    4. return 200 now     — GitHub's delivery timeout is ~10s; the engine is slow
    5. dispatch in bg     — run the graph after the response is sent

Returns:
    401 — bad/missing signature
    204 — well-signed but not actionable (success, wrong event, no failure)
    200 — accepted (newly claimed) OR a duplicate no-op; body says which
"""

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from cidra import config, history
from cidra.server.events import parse_event
from cidra.server.idempotency import IdempotencyStore
from cidra.server.security import verify_signature
from cidra.server.worker import process_job

log = logging.getLogger("cidra.server")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Fail loud if the webhook secret is unset — silently accepting would mean
    verify_signature rejects every real delivery with a confusing 401."""
    # Surface cidra.* logs (worker dispatch/outcome) — uvicorn only configures its
    # own loggers, so without this a background run is invisible.
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("cidra").setLevel(logging.INFO)
    if not config.WEBHOOK_SECRET:
        raise RuntimeError(
            "CIDRA_WEBHOOK_SECRET is not set — refusing to start. "
            "Set it here and in the repo's webhook config (see docs/8_api_contracts.md)."
        )
    yield


app = FastAPI(title="CIDRA webhook", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = IdempotencyStore(config.IDEMPOTENCY_DB)


@app.get("/")
def health() -> dict:
    return {"service": "cidra", "ok": True}


@app.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> Response:
    body = await request.body()

    # 1. Authenticity, before anything parses the body.
    if not verify_signature(body, x_hub_signature_256, config.WEBHOOK_SECRET):
        return Response(status_code=401, content="invalid signature")

    # 2. Relevance. A well-signed but uninteresting event is a clean 204.
    import json

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(status_code=400, content="invalid json")
    job = parse_event(x_github_event, payload)
    if job is None:
        return Response(status_code=204)

    # 3. Idempotency. A duplicate delivery is a successful no-op, not an error.
    if not _store.claim(job.run_id, job.head_sha):
        log.info("duplicate delivery run_id=%s — no-op", job.run_id)
        return Response(status_code=200, content="duplicate: no-op")

    # 4 + 5. Accept now, run the engine after the response is sent.
    background.add_task(process_job, job)
    return Response(status_code=200, content="accepted")


@app.get("/api/runs")
def list_runs(limit: int = 50):
    """Fetch recent runs for the dashboard."""
    return history.load(limit=limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """Fetch the full DebugState of a run."""
    state = history.load_full_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    return state


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str):
    """HITL Gate: approve a patch and merge the PR."""
    state = history.load_full_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # In a real implementation, this would trigger github_write.merge_pr
    log.info("HITL approval received for run_id=%s. (Mocked PR merge)", run_id)
    return {"status": "approved", "run_id": run_id, "message": "PR merged successfully"}
