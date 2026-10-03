"""Conditional edges. Pure functions, no I/O. See docs/4_architecture.md §6."""

from cidra.config import MAX_ANALYSIS_ATTEMPTS, MAX_FIX_ATTEMPTS
from cidra.state import DebugState


def route_after_validate(state: DebugState) -> str:
    analysis = state.get("analysis")
    is_flaky = analysis is not None and analysis.category == "flaky_test"
    # Refused categories go straight to the report. flaky_test is refused for
    # *patching* only; it still takes the detection path, which never patches.
    if state.get("policy_decision") == "strict_refusal" and not is_flaky:
        return "compose_report"
    if analysis is not None:
        return "checkout_commit"  # Phase 9: isolated checkout runs before sandbox
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
    # Phase 8: localize (SBFL) runs on a confirmed-red repro, before the fix path.
    return "localize" if state.get("reproduced") else "compose_report"


def route_after_strategy(state: DebugState) -> str:
    """No strategy means no repair path exists for this category (e.g. unknown).

    Without this, an out-of-scope failure still burns MAX_FIX_ATTEMPTS LLM calls
    before reaching the same diagnosis_only outcome.

    Phase 11: a cache hit already set fix_diff, so skip generate_fix (the LLM) and
    go straight to the audit gate — the diff is still audited and re-verified.
    """
    if not state.get("fix_strategy"):
        return "compose_report"
    if state.get("cache_hit") and state.get("fix_diff"):
        return "audit_patch"
    return "generate_fix"


def route_after_audit(state: DebugState) -> str:
    """A patch that fails the AST policy checks never reaches the sandbox.

    A rejected diff routes straight to the report (→ diagnosis_only): "no safe
    fix found" is the honest outcome, not applying an unsafe patch. See Phase 10
    and docs/threat/security_requirements.md SR-13/14/15.
    """
    return "apply_patch" if state.get("patch_audit_ok") else "compose_report"


def route_after_verify(state: DebugState) -> str:
    if state.get("verified"):
        return "compose_report"
    if state.get("fix_attempts", 0) < MAX_FIX_ATTEMPTS:
        return "generate_fix"
    return "compose_report"
