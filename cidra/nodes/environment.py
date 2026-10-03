"""Sandbox environment setup. See docs/4_architecture.md §5 nodes 5-7.

The Session outlives these three nodes, so it cannot live in DebugState (which
must stay serialisable). It is held in a module-level registry keyed by run_id
and torn down by publish.cleanup.
"""

import pathlib
import re
import shlex

import yaml

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
    # source_dir now points at the .git-free sandbox tree, so remember the real
    # repo separately: the PR path needs a clone it can commit and push from.
    out = {"source_dir": str(tree), "repo_dir": str(raw_source)}
    if "ci_env" not in state:  # a caller-supplied env (tests, eval) wins
        out["ci_env"] = workflow_env(tree, state.get("workflow_file"))
    return out


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def workflow_env(tree: pathlib.Path, workflow_file: str | None = None) -> dict[str, str]:
    """Literal `env:` values the repo's CI workflow sets, so the sandbox sees them.

    Without this a test that reads a CI-provided variable fails in the sandbox on
    every commit, and no fix can ever verify green. Read from the checked-out
    tree, i.e. the failing commit. Values holding a `${{ }}` expression (secrets,
    contexts) are skipped: CIDRA cannot and must not resolve them.
    """
    # ponytail: with no workflow_file, every workflow's env is merged (sorted,
    # later wins). Narrow to the failing workflow's path if that ever misfires.
    root = pathlib.Path(tree)
    if workflow_file and (root / workflow_file).is_file():
        files = [root / workflow_file]
    else:
        folder = root / ".github" / "workflows"
        files = sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")])

    env: dict[str, str] = {}

    def take(block) -> None:
        if not isinstance(block, dict):
            return
        for name, value in block.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            if (isinstance(name, str) and _ENV_NAME.match(name)
                    and isinstance(value, (str, int, float)) and "${{" not in str(value)):
                env[name] = str(value)

    for path in files:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue  # an unreadable workflow just contributes nothing
        if not isinstance(doc, dict):
            continue
        take(doc.get("env"))
        jobs = doc.get("jobs")
        for job in (jobs.values() if isinstance(jobs, dict) else []):
            if not isinstance(job, dict):
                continue
            take(job.get("env"))
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    take(step.get("env"))
    return env


def env_prefix(state: DebugState) -> str:
    """`K=V ` pairs to put in front of the test command. CIDRA-authored: names are
    validated and values quoted, so repo-supplied text is data, never shell syntax."""
    env = state.get("ci_env") or {}
    return "".join(
        f"{k}={shlex.quote(str(v))} " for k, v in sorted(env.items()) if _ENV_NAME.match(k)
    )


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
