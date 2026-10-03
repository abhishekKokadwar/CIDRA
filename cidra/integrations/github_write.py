"""GitHub write path. The ONLY module that mutates the repo. Phase 6, step 6.2.

Deliberately separate from github.py (read-only). github.py holds the
read-only token and does only GETs; this module holds CIDRA_GITHUB_TOKEN
(Contents:rw, Pull requests:rw) and is the only place a write can originate.
That is SR-06 / threat-model Rule 1 enforced by a module boundary, not a
convention: the node that ingests an untrusted CI log never imports this.

Idempotency: CIDRA finds its own prior comment by the hidden marker in the body
(report._MARKER) and PATCHes it instead of posting a new one. A re-run — or a
duplicate webhook delivery in Phase 7 — updates one comment rather than spamming
the thread.
"""

import httpx

from cidra.config import GITHUB_API, GITHUB_TOKEN
from cidra.nodes.report import _MARKER


def _client() -> httpx.Client:
    if not GITHUB_TOKEN:
        raise ValueError("CIDRA_GITHUB_TOKEN (write) is not set")
    return httpx.Client(
        base_url=GITHUB_API,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )


def _find_own_comment(c: httpx.Client, repo: str, issue: int) -> int | None:
    """The id of CIDRA's existing comment on this issue/PR, if any.

    Pages through comments: on a busy PR our comment can be past page 1, and
    missing it means double-posting instead of updating (idempotency depends on
    finding it). Bounded at 10 pages (1000 comments) so a pathological thread
    can't spin forever.
    """
    for page in range(1, 11):
        r = c.get(f"/repos/{repo}/issues/{issue}/comments",
                  params={"per_page": 100, "page": page})
        r.raise_for_status()
        batch = r.json()
        for comment in batch:
            if _MARKER in comment.get("body", ""):
                return comment["id"]
        if len(batch) < 100:
            break
    return None


def _default_branch(c: httpx.Client, repo: str) -> str:
    r = c.get(f"/repos/{repo}")
    r.raise_for_status()
    return r.json().get("default_branch", "main")


def open_draft_pr(repo: str, head_branch: str, title: str, body: str,
                  base: str | None = None) -> str:
    """Open a DRAFT PR for `head_branch`, or return the existing one's URL.

    Draft, never a merge — SR-11: CIDRA proposes, a human approves. Idempotent:
    a re-run whose branch already has an open PR returns that PR rather than
    erroring or opening a second.
    """
    with _client() as c:
        # Already open for this head? (owner:branch form for the query.)
        owner = repo.split("/")[0]
        existing = c.get(f"/repos/{repo}/pulls",
                         params={"head": f"{owner}:{head_branch}", "state": "open"})
        existing.raise_for_status()
        if existing.json():
            pr = existing.json()[0]
            # The branch was just re-pushed: keep the description in step with it.
            if pr.get("number") is not None:
                c.patch(f"/repos/{repo}/pulls/{pr['number']}", json={"body": body}).raise_for_status()
            return pr["html_url"]

        base = base or _default_branch(c, repo)
        r = c.post(f"/repos/{repo}/pulls", json={
            "title": title, "head": head_branch, "base": base,
            "body": body, "draft": True,
        })
        r.raise_for_status()
        return r.json()["html_url"]


def post_or_update_comment(repo: str, issue: int, body: str) -> str:
    """Post the comment, or update CIDRA's existing one. Returns its html_url.

    `issue` is the PR/issue number. GitHub treats PR comments as issue comments.
    `body` must already carry report._MARKER (render_comment adds it).
    """
    if _MARKER not in body:
        raise ValueError("comment body is missing the CIDRA marker; refusing to post")
    with _client() as c:
        existing = _find_own_comment(c, repo, issue)
        if existing is not None:
            r = c.patch(f"/repos/{repo}/issues/comments/{existing}", json={"body": body})
        else:
            r = c.post(f"/repos/{repo}/issues/{issue}/comments", json={"body": body})
        r.raise_for_status()
        return r.json()["html_url"]
