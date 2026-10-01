"""Background dispatch: run the engine for one webhook job. Phase 7, step 7.5.

Called from a FastAPI BackgroundTask after the request has already returned 200.
Assembles the initial DebugState and invokes the compiled graph. Because
issue_number is now supplied, the publish node posts a real comment instead of
dry-running (Phase 6, step 6.3).

Nothing here is allowed to crash the server: the whole run is wrapped so an
exception becomes a log line, not a 500 on a request that already succeeded.
The receiver claims the idempotency key *before* dispatching, so a run that
raises here releases its claim; redelivering the webhook then re-drives it
instead of being dropped as a duplicate.
"""

import logging

from cidra.server.events import WebhookJob, resolve_issue_number

log = logging.getLogger("cidra.worker")


def build_initial_state(job: WebhookJob) -> dict:
    """The DebugState seed for a run. The graph derives everything else."""
    return {
        "run_id": job.run_id,
        "repo": job.repo,
        "commit_sha": job.head_sha,
        "issue_number": resolve_issue_number(job),
    }


def process_job(job: WebhookJob) -> dict | None:
    """Run the engine for one job. Returns the terminal state, or None on error.

    Exceptions are logged and swallowed: this runs after the 200 response, so
    raising would only crash a background thread and lose the log.
    """
    from cidra.graph import build_graph

    state = build_initial_state(job)
    log.info("dispatch run_id=%s repo=%s issue=%s",
             state["run_id"], state["repo"], state.get("issue_number"))
    try:
        final = build_graph().invoke(state)
        log.info("done run_id=%s outcome=%s comment=%s",
                 state["run_id"], final.get("outcome"), final.get("comment_url"))
        return final
    except Exception:  # noqa: BLE001 - a background run must never take down the server
        log.exception("run failed run_id=%s", state["run_id"])
        _release_claim(job)
        return None


def _release_claim(job: WebhookJob) -> None:
    """Un-claim a crashed run so redelivering the webhook re-drives it."""
    try:
        from cidra.server import app  # lazy: app imports this module

        app._store.release(job.run_id, job.head_sha)
    except Exception:  # noqa: BLE001 - best-effort; never mask the original failure
        log.exception("could not release claim run_id=%s", job.run_id)
