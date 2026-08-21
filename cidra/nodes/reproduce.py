"""Reproduction. See docs/4_architecture.md §5 nodes 9-11.

Reproducing red is the precondition for claiming a fix: if the failure cannot be
made to happen here, nothing that follows can be verified.
"""

from cidra.config import FLAKY_RUNS, TEST_COMMAND
from cidra.nodes.environment import session_for
from cidra.state import DebugState


def _test_command(state: DebugState) -> str:
    """Prefix the CI env. CIDRA-authored — the LLM never contributes to this."""
    env = state.get("ci_env") or {}
    prefix = "".join(f"{k}={v} " for k, v in sorted(env.items()))
    return prefix + TEST_COMMAND


def reproduce_once(state: DebugState) -> dict:
    """One run. Red is the expected, desired outcome."""
    session = session_for(state["run_id"])
    if session is None:
        return {"reproduced": False}
    result = session.run("test", _test_command(state))
    return {
        "reproduced": not result.passed,
        "repro_results": [*state.get("repro_results", []), result],
    }


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
    passes = sum(r.passed for r in results)
    n = len(results)
    if 0 < passes < n:
        return {"flaky_pass_count": passes, "outcome": "flaky_detected"}
    if passes == n:
        return {"flaky_pass_count": passes, "reproduced": False}
    # All failed: LLM misclassified. Fall through to the normal fix path.
    return {"flaky_pass_count": 0, "reproduced": True}
