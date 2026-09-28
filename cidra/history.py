"""Run-history store. Phase 13.

One compact JSON summary per finished run, appended as a line to a JSONL file.
Every terminal path passes through publish.cleanup, which calls record() — so the
history is the durable trace of what CIDRA has done, and the Fleet TUI (and a
future dashboard) read it.

JSONL, not one big JSON array: append is a single write with no read-modify-write
race, and a corrupt trailing line never destroys the earlier history. Reads are
best-effort and skip unparseable lines — a damaged file degrades to "fewer rows",
never a crash. Recording is best-effort too: a history write must never take down
a run that otherwise succeeded.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel

from cidra import config
from cidra.state import DebugState

log = logging.getLogger("cidra.history")

# Only these fields are recorded — a summary, not the whole state. No secrets, no
# raw logs, no diffs (those live in the comment/PR); this is the index over runs.
_FIELDS = ("run_id", "repo", "commit_sha", "outcome", "category", "flaky_score",
           "cache_hit", "verified", "comment_url", "pr_url")


def summarize(state: DebugState) -> dict:
    """A flat, serialisable summary row for one run."""
    analysis = state.get("analysis")
    row = {
        "ts": round(time.time()),
        "run_id": state.get("run_id", ""),
        "repo": state.get("repo", ""),
        "commit_sha": (state.get("commit_sha") or "")[:12],
        "outcome": state.get("outcome", "failed"),
        "category": analysis.category if analysis is not None else None,
        "flaky_score": state.get("flaky_score"),
        "cache_hit": bool(state.get("cache_hit", False)),
        "verified": bool(state.get("verified", False)),
        "comment_url": state.get("comment_url"),
        "pr_url": state.get("pr_url"),
    }
    return row


class StateEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        return super().default(obj)

def save_full_state(state: DebugState):
    run_id = state.get("run_id")
    if not run_id:
        return
    
    state_to_save = dict(state)
    state_to_save.pop("raw_log", None)
    
    states_dir = Path("run_states")
    states_dir.mkdir(exist_ok=True)
    
    p = states_dir / f"{run_id}.json"
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(state_to_save, f, cls=StateEncoder, indent=2)
    except OSError as e:
        log.warning("could not save full state to %s: %s", p, e)

def load_full_state(run_id: str) -> Optional[dict]:
    p = Path(f"run_states/{run_id}.json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError):
        return None

def record(state: DebugState, path: str | Path | None = None) -> bool:
    """Append a run summary. Best-effort: returns False on any I/O error, never raises."""
    p = Path(path or config.RUN_HISTORY_PATH)
    
    save_full_state(state)
    
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summarize(state)) + "\n")
        return True
    except OSError as e:
        log.warning("run history not writable (%s): %s", p, e)
        return False


def load(limit: Optional[int] = None, path: str | Path | None = None) -> list[dict]:
    """Recent runs, newest first. Unparseable lines are skipped, not fatal."""
    p = Path(path or config.RUN_HISTORY_PATH)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    rows = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue  # a damaged line drops out; the rest survive
    rows.reverse()  # newest first
    return rows[:limit] if limit else rows
