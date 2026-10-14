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

import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from cidra import config
from cidra.git_ops import git


def _rmtree(path: Path) -> None:
    """Delete a directory tree, read-only files included.

    git marks its object files read-only, and on Windows shutil.rmtree cannot
    delete those, so `ignore_errors=True` used to leave .git behind without a word.
    Raises if something still cannot be removed.
    """
    def unlock(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=unlock)


def _run_dir(run_id: str) -> Path:
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_") or "run"
    # Absolute: callers run git with cwd=<this dir> and pass paths under it, and a
    # relative root (the default "worktrees") would then resolve twice.
    return Path(config.WORKTREE_ROOT).resolve() / f"cidra-patch-{safe}"


def source_run_id(run_id: str) -> str:
    """Where fetch_commit puts a run's source; remove_checkout(source_run_id(...)) drops it."""
    return f"{run_id}-src"


def remote_url(repo: str) -> str:
    """The repository's https URL on the configured GitHub host. `repo` is validated
    as owner/name by the first node, so nothing else can be spliced in here."""
    api = config.GITHUB_API
    host = "github.com" if "api.github.com" in api else api.split("://")[-1].split("/")[0]
    return f"https://{host}/{repo}.git"


def fetch_commit(run_id: str, repo: str, sha: str, token: str = "") -> Path:
    """Fetch one commit of a GitHub repository, for a run with no local checkout.

    Webhook mode needs this: the event names a repository and a commit, and
    nothing on this machine holds them. The token is given to the single fetch
    through git's GIT_CONFIG_* environment, so it is never written to
    .git/config, never on a command line, and never in the tree prepare_checkout
    later hands to the sandbox. Shallow: only the failing commit is needed.
    """
    import base64

    dest = _run_dir(source_run_id(run_id))
    remove_checkout(source_run_id(run_id))
    dest.mkdir(parents=True)
    url = remote_url(repo)
    env = {}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader",
               "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"}
    git("init", "--quiet", cwd=dest)
    # A local path stands in for GitHub in tests; a real run always fetches https.
    git("fetch", "--quiet", "--depth=1", "--no-recurse-submodules", url, sha,
        cwd=dest, timeout=300, env=env, allow_file=not url.startswith("https://"))
    git("checkout", "--quiet", "FETCH_HEAD", cwd=dest)
    return dest


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
            logging.getLogger("cidra.checkout").warning(
                "commit %s is not in %s; reproducing on its checked-out HEAD instead",
                commit_sha, source)

    if not keep_git:
        # SR-17: strip .git so nothing ever runs inside an attacker-supplied .git
        # and no .git reaches the container. shutil, not git — it is now inert data.
        git_dir = dest / ".git"
        if git_dir.exists():
            _rmtree(git_dir)  # raises if .git cannot be removed: never hand it on
    return dest


def remove_checkout(run_id: str) -> None:
    """Delete a run's checkout dir. Safe to call when it doesn't exist."""
    try:
        _rmtree(_run_dir(run_id))
    except OSError:
        logging.getLogger("cidra.checkout").warning("could not fully remove %s", _run_dir(run_id))
