"""GitHub Actions API. The only module that talks to github.com.

Read-only: every call here is a GET, and they use GITHUB_TOKEN_RO — a PAT with
Actions:read + Contents:read. A CI log is untrusted input, so the code that
reads one holds a token that cannot write. Repo mutation (Phase 6) belongs in
its own module with the write-scoped token.

The logs endpoint 302s to a signed blob URL that must be fetched WITHOUT the
Authorization header — forwarding it leaks the token to Azure. httpx forwards
headers across redirects by default, so redirects are handled manually.
"""

import io
import zipfile

import httpx

from cidra.config import GITHUB_API, GITHUB_TOKEN_RO

# GitHub streams the whole job archive; a runaway log shouldn't eat all memory.
MAX_ZIP_BYTES = 50 * 1024 * 1024


def _client() -> httpx.Client:
    """Read-only client. Everything in this module is a GET."""
    if not GITHUB_TOKEN_RO:
        raise ValueError("CIDRA_GITHUB_TOKEN_RO / CIDRA_GITHUB_TOKEN is not set")
    return httpx.Client(
        base_url=GITHUB_API,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN_RO}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )


def get_run(repo: str, run_id: int | str) -> dict:
    """Run metadata: head_sha, head_branch, conclusion, path to the workflow."""
    with _client() as c:
        r = c.get(f"/repos/{repo}/actions/runs/{run_id}")
        r.raise_for_status()
        return r.json()


def open_pr_for_commit(repo: str, sha: str) -> tuple[int, str] | None:
    """(number, head branch) of an open pull request that contains `sha`.

    The workflow_run payload often lists no pull requests even when one exists,
    so the caller asks here. Only a PR whose branch lives in `repo` counts: a
    fork's branch cannot be pushed to. The PR's head may have moved past `sha`
    (a second CI run of the same commit, after a fix was pushed): it is still
    the right thread to report on, and the non-forced push will be refused.
    """
    with _client() as c:
        r = c.get(f"/repos/{repo}/commits/{sha}/pulls")
        r.raise_for_status()
        for pr in r.json():
            head = pr.get("head") or {}
            if pr.get("state") == "open" and (head.get("repo") or {}).get("full_name") == repo:
                return pr["number"], head["ref"]
    return None


def failed_steps(repo: str, run_id: int | str) -> list[tuple[str, str]]:
    """(job_name, step_name) for every failed step, in run order.

    Used to pick log files out of the archive: a run's zip holds every step of
    every job, and the runner boilerplate around the failure is mostly noise.
    """
    with _client() as c:
        r = c.get(f"/repos/{repo}/actions/runs/{run_id}/jobs", params={"per_page": 100})
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    return [
        (job["name"], step["name"])
        for job in jobs
        for step in job.get("steps", [])
        if step.get("conclusion") == "failure"
    ]


def _download_logs(repo: str, run_id: int | str) -> bytes:
    """Fetch the run's log archive. Returns raw zip bytes."""
    with _client() as c:
        # follow_redirects stays off: the redirect target is a signed blob URL
        # that already carries its own auth, and our token must not follow.
        r = c.get(f"/repos/{repo}/actions/runs/{run_id}/logs")
        if r.status_code in (301, 302, 307, 308):
            url = r.headers["location"]
            with httpx.Client(timeout=120.0) as anon:  # no Authorization header
                r = anon.get(url, follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > MAX_ZIP_BYTES:
            raise ValueError(f"log archive too large: {len(r.content)} bytes")
        return r.content


def _pick(names: list[str], wanted: list[tuple[str, str]]) -> list[str]:
    """Archive members for the failed steps, else every whole-job log.

    Two layouts occur. Per-step files live in a job folder ("test/5_Run
    tests.txt"); whole-job files sit at the root ("0_test.txt"). Which one you
    get varies by run, so handle both. "<job>/system.txt" is runner
    diagnostics — never a failure signal — and is always dropped.
    """
    names = [n for n in names if not n.endswith("/system.txt")]
    hits = [n for n in names if any(f"_{step}.txt" in n for _, step in wanted)]
    if hits:
        return sorted(hits)
    # No per-step split in this archive: take the whole-job logs at the root.
    return sorted(n for n in names if "/" not in n)


def fetch_run_log(repo: str, run_id: int | str) -> str:
    """The failing portion of a run's logs, as one string.

    Falls back to the complete archive when no step is marked failed (a job
    that was cancelled or timed out reports no failing step).
    """
    try:
        wanted = failed_steps(repo, run_id)
    except httpx.HTTPError:
        wanted = []

    with zipfile.ZipFile(io.BytesIO(_download_logs(repo, run_id))) as z:
        names = [n for n in z.namelist() if n.endswith(".txt")]
        chosen = _pick(names, wanted) or sorted(names)
        parts = [
            f"##[cidra-file]{n}\n" + z.read(n).decode("utf-8", errors="replace")
            for n in chosen
        ]
    return "\n".join(parts)
