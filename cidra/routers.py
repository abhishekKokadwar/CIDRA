"""Conditional edges. Pure functions, no I/O. See docs/4_architecture.md §6."""

from cidra.config import MAX_ANALYSIS_ATTEMPTS, MAX_FIX_ATTEMPTS
from cidra.state import DebugState


def route_after_validate(state: DebugState) -> str:
    if state.get("analysis") is not None:
        return "prepare_sandbox"
    if state.get("analysis_attempts", 0) < MAX_ANALYSIS_ATTEMPTS:
        return "analyze"
    return "compose_report"


def route_after_env(state: DebugState) -> str:
    return "route_category" if state.get("env_ready") else "compose_report"


def route_category(state: DebugState) -> str:
    analysis = state.get("analysis")
    if analysis is not None and analysis.category == "flaky_test":
        return "reproduce_n_times"
    return "reproduce_once"


def route_after_flaky(state: DebugState) -> str:
    if state.get("outcome") == "flaky_detected":
        return "compose_report"
    # passes == 0 means the LLM misclassified: fall through to the normal path.
    return "reproduce_once" if state.get("reproduced") else "compose_report"


def route_after_reproduce(state: DebugState) -> str:
    return "select_strategy" if state.get("reproduced") else "compose_report"


def route_after_strategy(state: DebugState) -> str:
    """No strategy means no repair path exists for this category (e.g. unknown).

    Without this, an out-of-scope failure still burns MAX_FIX_ATTEMPTS LLM calls
    before reaching the same diagnosis_only outcome.
    """
    return "generate_fix" if state.get("fix_strategy") else "compose_report"


def route_after_verify(state: DebugState) -> str:
    if state.get("verified"):
        return "compose_report"
    if state.get("fix_attempts", 0) < MAX_FIX_ATTEMPTS:
        return "generate_fix"
    return "compose_report"
