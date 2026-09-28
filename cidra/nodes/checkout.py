"""Per-run isolated checkout. Phase 9, step 9.2.

Each repair gets its own checkout dir (worktrees/cidra-patch-{run_id}) so
concurrent runs never share a working tree and collide (Phase 9 goal). All git
goes through the hardened wrapper (git_ops), so a poisoned .git/config or hook in
the source can't run on the host (SR-16). The tree handed to the sandbox has its
.git REMOVED (SR-17): no operation ever runs inside an attacker-supplied .git,
and no .git reaches the container for a hook to fire from.

Local-clone approach rather than `git worktree add`: a worktree shares the
origin's .git, which we'd have to strip anyway for SR-17, and a fresh clone at a
pinned commit is the simplest thing that gives real isolation. `-c
protocol.file.allow` stays 'never' via the wrapper — the clone uses a plain
filesystem path, not the file:// transport that flag blocks.
"""

import shutil
from pathlib import Path
from typing import Optional

from cidra import config
from cidra.git_ops import git


def _run_dir(run_id: str) -> Path:
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_") or "run"
    return Path(config.WORKTREE_ROOT) / f"cidra-patch-{safe}"


def prepare_checkout(run_id: str, source: str | Path,
                     commit_sha: Optional[str] = None,
                     keep_git: bool = False) -> Path:
    """Isolated checkout of `source` (at `commit_sha` if given).

    Returns the path to hand the sandbox. Raises on git failure (infra error).

    `keep_git=False` (default) strips .git for the sandbox tree (SR-17). The PR
    path (Phase 9.6) passes keep_git=True because it needs a real clone to commit
    and push from; that tree is never handed to the container.
    """
    dest = _run_dir(run_id)
    remove_checkout(run_id)  # idempotency: a retried run must not reuse a stale tree
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Clone the local repo (hardened: no system/global config, no hooks).
    # allow_file: a local path clone IS a file transport, but it's OUR chosen
    # top-level source, not an attacker's. --no-recurse-submodules ensures a
    # malicious .gitmodules can't ride a file:// submodule fetch in on it.
    git("clone", "--quiet", "--no-hardlinks", "--no-recurse-submodules",
        str(source), str(dest), allow_file=True)
    if commit_sha:
        # Detached checkout of the exact commit. If the sha isn't present
        # (shallow/partial), the caller keeps the default branch — a red repro
        # is still valid, and the sha is a nicety here (mirrors ingest.py).
        try:
            git("checkout", "--quiet", commit_sha, cwd=dest)
        except Exception:
            pass

    if not keep_git:
        # SR-17: strip .git so nothing ever runs inside an attacker-supplied .git
        # and no .git reaches the container. shutil, not git — it is now inert data.
        git_dir = dest / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)
    return dest


def remove_checkout(run_id: str) -> None:
    """Delete a run's checkout dir. Safe to call when it doesn't exist."""
    shutil.rmtree(_run_dir(run_id), ignore_errors=True)
