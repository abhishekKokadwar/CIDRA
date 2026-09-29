"""Log ingestion. See docs/4_architecture.md §5 nodes 1-2.

isolate_error is pure — the free/instant Tier 1 eval surface (docs/5_fixtures.md §6).
"""

import re

from cidra.config import ERROR_MARKERS, LOG_LINES_AFTER, LOG_LINES_BEFORE
from cidra.state import DebugState

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
# GitHub Actions prefixes every line with an ISO timestamp.
_TIMESTAMP = re.compile(r"^\S*\d{4}-\d{2}-\d{2}T[\d:.]+Z?\s?")
# Fold/echo directives are runner chrome. ##[error] is dropped from this set on
# purpose — it is GitHub's own annotation of the failure and the best marker in
# the file, so _clean keeps it and ERROR_MARKERS anchors on it.
_DIRECTIVE = re.compile(r"^##\[(?:endgroup|group|command|debug|section)\]")


def fetch_log(state: DebugState) -> dict:
    """Pull the failing job's log from GitHub Actions.

    A fixture that already supplied raw_log wins, which keeps the Tier 1/Tier 2
    eval suites offline and token-free.
    """
    if state.get("raw_log"):
        return {}
    repo, run_id = state.get("repo"), state.get("run_id")
    if not repo or not run_id:
        return {"analysis_error": "no raw_log and no repo/run_id to fetch one"}

    from cidra.integrations.github import fetch_run_log, get_run

    try:
        raw = fetch_run_log(repo, run_id)
    except Exception as e:
        return {"analysis_error": f"log fetch failed: {type(e).__name__}: {e}"[:500]}

    out: dict = {"raw_log": raw}
    if not state.get("commit_sha"):
        try:
            run = get_run(repo, run_id)
            out["commit_sha"] = run["head_sha"]
            out["workflow_file"] = run.get("path")
        except Exception:
            pass  # the log is what matters; sha is a nicety here
    return out


def isolate_error(state: DebugState) -> dict:
    """Use the Language Adapter to parse and normalize the raw log."""
    from cidra.adapters.dispatcher import dispatcher
    
    raw_log = state.get("raw_log", "")
    if not raw_log:
        return {"error_region": "", "log_markers": []}
        
    failure = dispatcher.parse_log(raw_log)
    
    # If the adapter failed to recognize the log, handle gracefully
    if failure.language == "unknown":
        return {"analysis_error": "unsupported_or_unrecognized_failure"}
        
    # Return both the full FailureEvent object mapping and the legacy keys
    # so we don't break existing graph operations (Tier 1 vs Tier 2, etc.)
    out = failure.to_dict()
    
    # Backwards compatibility for CIDRA Core
    out["error_region"] = failure.stack_trace
    out["log_markers"] = failure.log_markers
    
    return out
