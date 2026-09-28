"""Replay a GitHub workflow_run delivery against a local CIDRA server.

Drives the FULL pipeline — real HMAC, real graph, real Docker sandbox, real
comment — without a public tunnel. It sends exactly what GitHub sends: the same
raw JSON body, signed with CIDRA_WEBHOOK_SECRET, and the workflow_run headers.
The only thing it does NOT prove is that GitHub's own POST reached the box; that
is pure transport.

Usage (server running: `uvicorn cidra.server.app:app --port 8000`):

    # From a real failed run on your repo — most faithful:
    export CIDRA_WEBHOOK_SECRET=...            # same secret the server uses
    python scripts/replay_delivery.py --repo helpmecode69/cidra-practice --run-id 12345678

    # From a canned sample (no GitHub call; won't fetch real logs downstream):
    python scripts/replay_delivery.py --sample --repo o/r --run-id 999 --sha abc123

    # Prove idempotency: send the same delivery twice, expect accepted then no-op:
    python scripts/replay_delivery.py --repo ... --run-id ... --twice

`--run-id` without `--sample` fetches the run's real head_sha and pull_requests
via the read-only token, so the payload matches what GitHub would have sent and
the server's downstream log fetch works against a genuine run.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cidra.server.security import sign  # noqa: E402


def _payload_from_github(repo: str, run_id: str) -> dict:
    """Build a workflow_run payload from a real run (read-only token)."""
    from cidra.integrations.github import get_run

    run = get_run(repo, run_id)
    prs = [{"number": pr["number"]} for pr in run.get("pull_requests", [])]
    return {
        "action": "completed",
        "repository": {"full_name": repo},
        "workflow_run": {
            "id": int(run_id),
            "head_sha": run["head_sha"],
            "conclusion": run.get("conclusion", "failure"),
            "pull_requests": prs,
        },
    }


def _payload_sample(repo: str, run_id: str, sha: str, issue: int | None) -> dict:
    return {
        "action": "completed",
        "repository": {"full_name": repo},
        "workflow_run": {
            "id": int(run_id),
            "head_sha": sha,
            "conclusion": "failure",
            "pull_requests": [{"number": issue}] if issue else [],
        },
    }


def _deliver(url: str, body: bytes, secret: str) -> httpx.Response:
    return httpx.post(
        url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-Hub-Signature-256": sign(body, secret),
            "X-GitHub-Delivery": "replay-0001",
        },
        timeout=30.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/webhook")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sha", help="head_sha (required with --sample)")
    ap.add_argument("--issue", type=int, help="PR number to force (sample only)")
    ap.add_argument("--sample", action="store_true",
                    help="build a canned payload instead of fetching the real run")
    ap.add_argument("--twice", action="store_true",
                    help="send the same delivery twice to demonstrate idempotency")
    args = ap.parse_args()

    secret = os.environ.get("CIDRA_WEBHOOK_SECRET", "")
    if not secret:
        print("CIDRA_WEBHOOK_SECRET is not set — set the same value the server uses.")
        return 2

    if args.sample:
        if not args.sha:
            print("--sample requires --sha")
            return 2
        payload = _payload_sample(args.repo, args.run_id, args.sha, args.issue)
    else:
        payload = _payload_from_github(args.repo, args.run_id)

    # Sign the EXACT bytes we send — canonicalised once, reused for sig and body.
    body = json.dumps(payload).encode()

    r = _deliver(args.url, body, secret)
    print(f"1st delivery: {r.status_code} {r.text!r}")
    if args.twice:
        r2 = _deliver(args.url, body, secret)
        print(f"2nd delivery: {r2.status_code} {r2.text!r}  (expect 200 'duplicate: no-op')")
        ok = r.status_code == 200 and r2.status_code == 200 and "duplicate" in r2.text
        return 0 if ok else 1
    return 0 if r.status_code in (200, 204) else 1


if __name__ == "__main__":
    raise SystemExit(main())
