"""Reproduction. See docs/4_architecture.md §5 nodes 9-11.

Reproducing red is the precondition for claiming a fix: if the failure cannot be
made to happen here, nothing that follows can be verified.
"""

from cidra.config import FLAKY_RUNS, FLAKY_SCORE_THRESHOLD
from cidra.nodes.environment import sandbox_test_command, session_for
from cidra.state import DebugState, SandboxResult

# Exit codes that mean the runner itself did not work, not that a test failed:
# pytest 3 = internal error, 4 = usage error, 5 = no tests collected;
# shell 126 = not executable, 127 = command not found.
# (pytest 1 = tests failed and 2 = collection error, e.g. a missing import —
# both are real failures.)
_RUNNER_ERROR_CODES = {3, 4, 5, 126, 127}


def _runner_error(result: SandboxResult) -> str | None:
    """Why this result is not evidence about the tests, or None if it is."""
    if result.step == "test" and result.exit_code in _RUNNER_ERROR_CODES:
        tail = (result.stdout_tail or result.stderr_tail).strip()[-200:]
        return f"test runner did not run (exit {result.exit_code}): {tail}"
    return None


def flakiness_score(passes: int, n: int) -> int:
    """Deterministic Flakiness Score, 0-100 (Phase 8).

    0   = unanimous (all pass or all fail) — deterministic, not flaky.
    100 = a perfect split (as many passes as fails) — maximally non-deterministic.
    Between: the closer the run outcomes are to 50/50, the higher the score.

        score = round(100 * (1 - |passes - fails| / n))

    This generalises the old binary "some passed and some failed" flip check into
    a measured degree, so the eval can report flake classification as a number.
    """
    if n <= 0:
        return 0
    fails = n - passes
    return round(100 * (1 - abs(passes - fails) / n))


def _test_command(state: DebugState) -> str:
    return sandbox_test_command(state)


def reproduce_once(state: DebugState) -> dict:
    """One run. Red is the expected, desired outcome."""
    session = session_for(state["run_id"])
    if session is None:
        return {"reproduced": False}
    result = session.run("test", _test_command(state))
    results = [*state.get("repro_results", []), result]
    error = _runner_error(result)
    if error:
        # A runner that never ran proves nothing: not reproduced, and say why.
        return {"reproduced": False, "repro_results": results, "analysis_error": error}
    return {"reproduced": not result.passed, "repro_results": results}


def reproduce_n_times(state: DebugState) -> dict:
    """FLAKY_RUNS identical runs. Inconsistency across them is the signal."""
    session = session_for(state["run_id"])
    if session is None:
        return {"reproduced": False}
    command = _test_command(state)
    results = [session.run("test", command) for _ in range(FLAKY_RUNS)]
    return {"repro_results": [*state.get("repro_results", []), *results]}


def classify_flakiness(state: DebugState) -> dict:
    """Pure. Some pass + some fail == non-deterministic.

    Reads only the last FLAKY_RUNS results so an earlier install/test result in
    the list cannot skew the count.
    """
    results = state.get("repro_results", [])[-FLAKY_RUNS:]
    if not results:
        return {"reproduced": False}
    for r in results:
        error = _runner_error(r)
        if error:
            return {"reproduced": False, "analysis_error": error}
    passes = sum(r.passed for r in results)
    n = len(results)
    score = flakiness_score(passes, n)

    if score >= FLAKY_SCORE_THRESHOLD and passes != n and passes != 0:
        # Non-deterministic: some passed, some failed. Isolate — 0 repair attempts.
        return {"flaky_pass_count": passes, "flaky_score": score,
                "outcome": "flaky_detected"}
    if passes == n:
        # Always green here: not the failure we were called for.
        return {"flaky_pass_count": passes, "flaky_score": score, "reproduced": False}
    # All failed (score 0): deterministic failure, LLM mislabeled it flaky.
    # Fall through to the normal fix path.
    return {"flaky_pass_count": 0, "flaky_score": score, "reproduced": True}
