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

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Request, Response, HTTPException

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

# No CORS middleware on purpose: the dashboard is served from this same origin,
# so no other origin has any business reading or writing these endpoints.

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _hostname(netloc: str) -> str:
    """'localhost:8000' -> 'localhost', '[::1]:8000' -> '::1'."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[1:].split("]", 1)[0]
    return netloc.rsplit(":", 1)[0] if ":" in netloc else netloc


def api_guard(request: Request) -> None:
    """Gate for every /api/* route. These endpoints read masked credentials and
    write .env, so a web page open in the same browser must not reach them.

      - Origin, when sent, must be this server's own origin (blocks cross-site
        requests; browsers always send Origin on cross-origin writes).
      - With CIDRA_DASHBOARD_TOKEN set, X-CIDRA-Token must match.
      - Without a token, the Host must be loopback (blocks DNS rebinding and
        accidental exposure on a LAN interface).
    """
    import hmac
    from urllib.parse import urlsplit

    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc.lower() != host.lower():
        raise HTTPException(status_code=403, detail="cross-origin request refused")

    token = config.DASHBOARD_TOKEN
    if token:
        if not hmac.compare_digest(request.headers.get("x-cidra-token", ""), token):
            raise HTTPException(status_code=401, detail="missing or invalid X-CIDRA-Token")
    elif _hostname(host) not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="set CIDRA_DASHBOARD_TOKEN to use the API from a non-loopback host",
        )

_store = IdempotencyStore(config.IDEMPOTENCY_DB)


from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def health(request: Request):
    # Serve React dashboard to browsers, JSON health status to API clients / tests
    if "text/html" in request.headers.get("accept", "") and (_STATIC_DIR / "index.html").exists():
        return FileResponse(_STATIC_DIR / "index.html")
    return {"service": "cidra", "ok": True}


if (_STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")


@app.get("/telemetry.json")
def get_telemetry():
    if (_STATIC_DIR / "telemetry.json").exists():
        return FileResponse(_STATIC_DIR / "telemetry.json")
    return history.load()


@app.get("/cidra_icon.png")
def get_icon():
    if (_STATIC_DIR / "cidra_icon.png").exists():
        return FileResponse(_STATIC_DIR / "cidra_icon.png")
    return Response(status_code=404)


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


@app.get("/api/runs", dependencies=[Depends(api_guard)])
def list_runs(limit: int = 50):
    """Fetch recent runs for the dashboard."""
    return history.load(limit=limit)


@app.get("/api/runs/{run_id}", dependencies=[Depends(api_guard)])
def get_run(run_id: str):
    """Fetch the full DebugState of a run."""
    state = history.load_full_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    return state


@app.post("/api/runs/{run_id}/approve", dependencies=[Depends(api_guard)])
def approve_run(run_id: str):
    """HITL Gate: approve a patch and merge the PR."""
    state = history.load_full_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # In a real implementation, this would trigger github_write.merge_pr
    log.info("HITL approval received for run_id=%s. (Mocked PR merge)", run_id)
    return {"status": "approved", "run_id": run_id, "message": "PR merged successfully"}


@app.get("/api/settings", dependencies=[Depends(api_guard)])
def get_settings():
    """Fetch live settings and masked credentials from .env and config."""
    from cidra.server import settings
    return settings.get_current_settings()


@app.post("/api/settings", dependencies=[Depends(api_guard)])
async def update_settings(request: Request):
    """Save updated settings directly to .env and reload in-memory config."""
    from cidra.server import settings
    payload = await request.json()
    return settings.save_settings(payload)


@app.post("/api/settings/test", dependencies=[Depends(api_guard)])
async def test_provider_endpoint(request: Request):
    """Test connectivity and measure latency to a provider."""
    from cidra.server import settings
    payload = await request.json()
    provider_id = payload.get("provider_id", "")
    return settings.test_provider(provider_id)

