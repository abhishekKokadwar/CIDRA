"""Sandbox environment setup. See docs/4_architecture.md §5 nodes 5-7.

The Session outlives these three nodes, so it cannot live in DebugState (which
must stay serialisable). It is held in a module-level registry keyed by run_id
and torn down by publish.cleanup.
"""

import pathlib

from cidra.config import PRACTICE_REPO_DIR
from cidra.sandbox.runner import Session
from cidra.state import DebugState

# run_id -> live Session. cleanup() is the only remover.
# ponytail: a dict is enough for one process; revisit if the server goes multi-worker.
_SESSIONS: dict[str, Session] = {}


def session_for(run_id: str) -> Session | None:
    return _SESSIONS.get(run_id)


def close_session(run_id: str) -> None:
    session = _SESSIONS.pop(run_id, None)
    if session is not None:
        session.__exit__(None, None, None)


def checkout_commit(state: DebugState) -> dict:
    """Isolated per-run checkout via the hardened git wrapper (Phase 9).

    Runs BEFORE prepare_sandbox. Clones the source into
    worktrees/cidra-patch-{run_id}, checks out the target commit, strips .git,
    and points `source_dir` at that tree. All git runs hardened (SR-16), and the
    tree has no .git (SR-17), so a poisoned repo can neither run a hook on the
    host nor smuggle a .git into the container.
    """
    from cidra.nodes.checkout import prepare_checkout

    run_id = state["run_id"]
    raw_source = state.get("source_dir") or PRACTICE_REPO_DIR
    try:
        tree = prepare_checkout(run_id, raw_source, state.get("commit_sha"))
    except Exception as e:
        return {"env_ready": False, "analysis_error": f"checkout failed: {e}"[:500]}
    return {"source_dir": str(tree)}


def prepare_sandbox(state: DebugState) -> dict:
    """Create the container from the run's isolated checkout (Phase 9).

    Consumes `source_dir` (the .git-free per-run tree checkout_commit produced),
    so concurrent runs never share a working tree. Nothing has network from here
    on except install.
    """
    if state.get("env_ready") is False:
        return {}  # a prior node (checkout) already failed; don't mask its error
    run_id = state["run_id"]
    close_session(run_id)  # idempotency: a retried run must not leak the old one
    source = pathlib.Path(state.get("source_dir") or PRACTICE_REPO_DIR)
    if not source.exists():
        return {"env_ready": False, "analysis_error": f"source not found: {source}"}
    try:
        _SESSIONS[run_id] = Session(source).__enter__()
    except Exception as e:
        return {"env_ready": False, "analysis_error": f"sandbox unavailable: {e}"[:500]}
    return {"image_tag": None}


def install_deps(state: DebugState) -> dict:
    """The ONLY step with network access. See docs/6_sandbox_spec.md §5."""
    session = session_for(state["run_id"])
    if session is None:
        return {"env_ready": False}
    result = session.install("pip install --quiet -r requirements.txt")
    return {
        "env_ready": result.passed,
        "repro_results": [*state.get("repro_results", []), result],
    }
