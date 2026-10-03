"""Draft-PR generation for a verified fix. Phase 9, step 9.6.

Runs only after verify_fix proved the patch green in the sandbox. Turns the
verified diff into a real branch (`cidra/patch-{run_id}`) and opens a **draft**
PR — never a merge (SR-11: CIDRA never merges; a human approves).

Two halves, tested separately:
  - build_fix_branch(): git side — clone WITH .git, apply the diff via the
    hardened wrapper, commit, push to the fix branch. All git is hardened
    (SR-16); the diff is applied as data, never executed (Rule 2).
  - open_draft_pr(): the single REST call, in the write module (SR-06: only the
    module holding the write token opens a PR).

The push uses a short-lived authenticated remote URL built at push time from the
write token. It is never logged and never stored on state.
"""

import logging
from pathlib import Path
from typing import Optional

from cidra.git_ops import git
from cidra.nodes.checkout import prepare_checkout, remove_checkout

log = logging.getLogger("cidra.pr")


def fix_branch_name(run_id: str) -> str:
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_") or "run"
    return f"cidra/patch-{safe}"


def _authenticated_remote(repo: str, token: str, api: str) -> str:
    # https://x-access-token:<token>@github.com/owner/name.git
    host = "github.com" if "api.github.com" in api else api.split("://")[-1]
    return f"https://x-access-token:{token}@{host}/{repo}.git"


def build_fix_branch(run_id: str, source: str | Path, diff: str,
                     repo: str, token: str, api: str,
                     base_sha: Optional[str] = None,
                     push: bool = True,
                     branch_name: Optional[str] = None) -> str:
    """Create the fix branch from `diff` and (optionally) push it. Returns branch.

    A dedicated clone WITH .git — separate from the sandbox tree — so we can
    commit and push. Never handed to the container.
    """
    branch = branch_name or fix_branch_name(run_id)
    pr_run = f"{run_id}-pr"
    # Always drop the PR clone, even if apply/commit/push raises — it holds an
    # authenticated remote and must never linger.
    try:
        tree = prepare_checkout(pr_run, source, base_sha, keep_git=True)

        git("checkout", "--quiet", "-B", branch, cwd=tree)
        # Apply the verified diff as DATA (Rule 2): write a file, git apply reads it.
        patch_file = Path(tree) / ".cidra.patch"
        patch_file.write_text(diff, encoding="utf-8")
        git("apply", "--ignore-whitespace", str(patch_file), cwd=tree)
        patch_file.unlink(missing_ok=True)

        git("add", "-A", cwd=tree)
        git("-c", "user.email=cidra@local", "-c", "user.name=CIDRA",
            "commit", "--quiet", "-m", f"CIDRA verified fix for run {run_id}", cwd=tree)

        if push:
            remote = _authenticated_remote(repo, token, api)
            # --force only for CIDRA's own cidra/patch-* branch, where a re-run
            # of the same run_id replaces its previous attempt. A contributor's
            # PR branch (branch_name given) is never forced: if they pushed
            # since the failing commit, the push is rejected rather than
            # overwriting their work.
            # allow_file so a local-path remote works (tests / self-hosted); a
            # real https github remote is unaffected by the flag.
            force = [] if branch_name else ["--force"]
            git("push", *force, "--quiet", remote, f"{branch}:{branch}",
                cwd=tree, allow_file=True)
        return branch
    finally:
        remove_checkout(pr_run)
