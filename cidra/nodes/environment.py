"""Sandbox environment setup. See docs/4_architecture.md §5 nodes 5-7.

The Session outlives these three nodes, so it cannot live in DebugState (which
must stay serialisable). It is held in a module-level registry keyed by run_id
and torn down by publish.cleanup.
"""

import pathlib
import re
import shlex

import yaml

from cidra import config
from cidra.config import PRACTICE_REPO_DIR
from cidra.sandbox import limits
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
    from cidra.nodes.checkout import fetch_commit, prepare_checkout

    run_id = state["run_id"]
    raw_source = state.get("source_dir")
    try:
        if not raw_source:
            # Webhook mode: nothing local holds the failing commit, so fetch it
            # with the read-only token.
            raw_source = fetch_commit(run_id, state["repo"], state["commit_sha"], config.GITHUB_TOKEN_RO)
        tree = prepare_checkout(run_id, raw_source, state.get("commit_sha"))
    except Exception as e:
        return {"env_ready": False, "analysis_error": f"checkout failed: {e}"[:500]}
    # source_dir now points at the .git-free sandbox tree, so remember the real
    # repo separately: the PR path needs a clone it can commit and push from.
    out = {"source_dir": str(tree), "repo_dir": str(raw_source)}
    if "ci_env" not in state:  # a caller-supplied env (tests, eval) wins
        out["ci_env"] = workflow_env(tree, state.get("workflow_file"))
    if "python_version" not in state:
        out["python_version"] = workflow_python(tree, state.get("workflow_file"))
    return out


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MATRIX_REF = re.compile(r"^\$\{\{\s*matrix\.([\w-]+)\s*\}\}$")


def _workflow_files(tree: pathlib.Path, workflow_file: str | None) -> list[pathlib.Path]:
    root = pathlib.Path(tree)
    if workflow_file and (root / workflow_file).is_file():
        return [root / workflow_file]
    folder = root / ".github" / "workflows"
    return sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")])


def _python_minor(value) -> str | None:
    """'3.8.10' -> '3.8'. An unquoted YAML 3.10 arrives as the float 3.1."""
    text = "3.10" if value == 3.1 and isinstance(value, float) else str(value).strip()
    m = re.match(r"^(3\.\d+)(\.\d+)?$", text)
    return m.group(1) if m else None


def workflow_python(tree: pathlib.Path, workflow_file: str | None = None) -> str:
    """The Python version the repo's CI runs on, so the sandbox matches it.

    Read from `actions/setup-python` in the workflow at the failing commit, then
    from a `.python-version` file. Anything unreadable or without a sandbox image
    falls back to the default.
    """
    # ponytail: for a version matrix the first entry is used, not the one whose
    # job failed. Pick it from the failing job's name if that ever misdiagnoses.
    found: list = []
    for path in _workflow_files(tree, workflow_file):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        for job in (jobs.values() if isinstance(jobs, dict) else []):
            if not isinstance(job, dict):
                continue
            strategy = job.get("strategy")
            matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
            for step in job.get("steps") or []:
                if not (isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/setup-python")):
                    continue
                value = (step.get("with") or {}).get("python-version")
                ref = _MATRIX_REF.match(str(value))
                if ref and isinstance(matrix, dict):
                    value = matrix.get(ref.group(1))
                found.extend(value if isinstance(value, list) else [value])
    pin = pathlib.Path(tree) / ".python-version"
    if pin.is_file():
        found.append(pin.read_text(encoding="utf-8", errors="replace").strip())
    for value in found:
        minor = _python_minor(value)
        if minor == limits.DEFAULT_PYTHON or minor in limits.PYTHON_IMAGES:
            return minor
    return limits.DEFAULT_PYTHON


def workflow_env(tree: pathlib.Path, workflow_file: str | None = None) -> dict[str, str]:
    """Literal `env:` values the repo's CI workflow sets, so the sandbox sees them.

    Without this a test that reads a CI-provided variable fails in the sandbox on
    every commit, and no fix can ever verify green. Read from the checked-out
    tree, i.e. the failing commit. Values holding a `${{ }}` expression (secrets,
    contexts) are skipped: CIDRA cannot and must not resolve them.
    """
    # ponytail: with no workflow_file, every workflow's env is merged (sorted,
    # later wins). Narrow to the failing workflow's path if that ever misfires.
    files = _workflow_files(tree, workflow_file)

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


def env_prefix(state: DebugState, skip: frozenset = frozenset()) -> str:
    """`K=V ` pairs to put in front of the test command. CIDRA-authored: names are
    validated and values quoted, so repo-supplied text is data, never shell syntax."""
    env = state.get("ci_env") or {}
    return "".join(
        f"{k}={shlex.quote(str(v))} " for k, v in sorted(env.items()) if _ENV_NAME.match(k) and k not in skip
    )


_EXTRA_REQUIREMENTS = ("requirements-dev.txt", "requirements-test.txt", "dev-requirements.txt", "test-requirements.txt")
_TEST_EXTRAS = ("test", "tests", "testing", "dev")


def detect_install(tree: pathlib.Path) -> str:
    """One `pip install` for a repository nobody configured (ROADMAP M4): its
    requirements files, else the package itself with its test extra, else
    nothing. The sandbox appends `--target`, so this stays a single pip call."""
    if (tree / "requirements.txt").is_file():
        files = ["requirements.txt", *(f for f in _EXTRA_REQUIREMENTS if (tree / f).is_file())]
        return "pip install --quiet " + " ".join(f"-r {f}" for f in files)
    if (tree / "pyproject.toml").is_file() or (tree / "setup.py").is_file():
        extras = {}
        try:
            import tomllib
            with open(tree / "pyproject.toml", "rb") as f:
                extras = tomllib.load(f).get("project", {}).get("optional-dependencies", {})
        except (OSError, ValueError):
            pass  # setup.py only, or a pyproject.toml that does not parse: install the package alone
        extra = next((e for e in _TEST_EXTRAS if e in extras), None)
        return f"pip install --quiet '.[{extra}]'" if extra else "pip install --quiet ."
    return "true"  # nothing to install; `true` ignores the --target the sandbox appends


def sandbox_install_command(state: DebugState) -> str:
    """The run's install command: the operator's, else one detected from the checkout."""
    return (state.get("install_command") or config.INSTALL_COMMAND
            or detect_install(pathlib.Path(state.get("source_dir") or PRACTICE_REPO_DIR)))


def sandbox_test_command(state: DebugState) -> str:
    """The run's test command behind its CI env. Operator-set; the LLM never contributes."""
    # Every run asks pytest for a per-test JUnit report (cidra/junit.py), on top of any
    # PYTEST_ADDOPTS the repo's CI sets. Exported, so it reaches pytest even behind
    # `cd sub && ...`; the old report is removed first so a run that writes none
    # cannot be read as the previous one's.
    addopts = f"{(state.get('ci_env') or {}).get('PYTEST_ADDOPTS', '')} --junitxml={limits.JUNIT}".strip()
    return (f"rm -f {limits.JUNIT}; export PYTEST_ADDOPTS={shlex.quote(addopts)}; "
            + env_prefix(state, skip=frozenset({"PYTEST_ADDOPTS"}))
            + (state.get("test_command") or config.TEST_COMMAND))


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
        session = _SESSIONS[run_id] = Session(source, state.get("python_version")).__enter__()
    except Exception as e:
        return {"env_ready": False, "analysis_error": f"sandbox unavailable: {e}"[:500]}
    return {"image_tag": f"{session.image}@{session.image_id}"}


def install_deps(state: DebugState) -> dict:
    """The ONLY step with network access. See docs/6_sandbox_spec.md §5."""
    session = session_for(state["run_id"])
    if session is None:
        return {"env_ready": False}
    result = session.install(sandbox_install_command(state))
    out = {"env_ready": result.passed, "repro_results": [*state.get("repro_results", []), result]}
    if not result.passed:
        # The most likely first failure on a new repository: say what went wrong (G-18).
        tail = (result.stderr_tail.strip() or result.stdout_tail.strip())[-600:]
        out["analysis_error"] = f"install failed (exit {result.exit_code}): {tail}"
    return out
