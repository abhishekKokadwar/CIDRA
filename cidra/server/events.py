"""Parse and filter a GitHub webhook payload. Phase 7, step 7.3.

CIDRA acts on exactly one thing: a workflow run that COMPLETED and FAILED.
Everything else — in-progress runs, successes, other event types — is ignored
with a 204 so GitHub stops retrying but no work happens.

The payload is untrusted (its authenticity is established upstream by the HMAC
check in security.py). This module only reads named fields; it never treats any
value as an instruction and never builds a command from one.

PR resolution: `workflow_run.pull_requests[]` carries the PR for same-repo runs
but is empty for fork PRs. When empty we look the PR up by head SHA through the
read-only client (a GET — the reader never holds a write token, SR-06). If
neither yields a PR, `issue_number` is None and publish dry-runs.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class WebhookJob:
    """The distilled, trusted-shape result of a relevant webhook."""

    repo: str  # "owner/name"
    run_id: str
    head_sha: str
    issue_number: Optional[int]  # PR to comment on; None ⇒ dry-run


def parse_event(event_type: str | None, payload: dict) -> Optional[WebhookJob]:
    """Return a WebhookJob for an actionable failure, else None (⇒ 204 skip).

    PR resolution here uses only the payload. The SHA-lookup fallback needs a
    network call, so it lives in resolve_issue_number(), called by the worker.
    """
    if event_type != "workflow_run":
        return None
    if payload.get("action") != "completed":
        return None

    run = payload.get("workflow_run") or {}
    if run.get("conclusion") != "failure":
        return None

    repo = (payload.get("repository") or {}).get("full_name")
    run_id = run.get("id")
    head_sha = run.get("head_sha")
    if not repo or run_id is None or not head_sha:
        return None

    prs = run.get("pull_requests") or []
    issue = prs[0].get("number") if prs and prs[0].get("number") else None

    return WebhookJob(repo=repo, run_id=str(run_id), head_sha=head_sha, issue_number=issue)


def resolve_issue_number(job: WebhookJob) -> Optional[int]:
    """Best-effort PR number for a job whose payload had none (fork PRs).

    Queries the PRs whose head is this SHA via the read-only client. Returns the
    first open PR's number, or None. Never raises — a failed lookup just means
    dry-run, which is a safe default, not an error.
    """
    if job.issue_number is not None:
        return job.issue_number
    try:
        from cidra.integrations.github import _client
    except Exception:
        return None
    try:
        with _client() as c:
            r = c.get(
                f"/repos/{job.repo}/commits/{job.head_sha}/pulls",
                headers={"Accept": "application/vnd.github+json"},
            )
            r.raise_for_status()
            pulls = r.json()
    except Exception:
        return None
    for pr in pulls:
        if pr.get("state") == "open" and pr.get("number"):
            return pr["number"]
    # No open PR from head SHA: accept a closed/merged one only if it's the sole hit.
    if len(pulls) == 1 and pulls[0].get("number"):
        return pulls[0]["number"]
    return None
