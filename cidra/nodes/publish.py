"""Output. See docs/4_architecture.md §5 nodes 16-18. Phase 6."""

from cidra.state import DebugState


def compose_report(state: DebugState) -> dict:
    """Pure. Never claims a fix that wasn't verified."""
    if state.get("outcome"):
        outcome = state["outcome"]
    elif state.get("verified"):
        outcome = "verified_fix"
    elif state.get("analysis") is None:
        outcome = "failed"
    elif not state.get("reproduced"):
        outcome = "failed"
    else:
        outcome = "diagnosis_only"
    return {"outcome": outcome, "final_output": f"outcome={outcome}"}


def publish(state: DebugState) -> dict:
    return {}


def cleanup(state: DebugState) -> dict:
    """Runs on every terminal path. Destroys the container.

    Every route to END passes through here (arch §4), so this is the one place
    that guarantees no container outlives a run.
    """
    from cidra.nodes.environment import close_session

    close_session(state.get("run_id", ""))
    return {}
