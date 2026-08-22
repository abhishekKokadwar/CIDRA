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


def _clean(line: str) -> str:
    line = line.lstrip("﻿")  # GitHub emits a BOM on the first log line
    line = _ANSI.sub("", line)
    line = _TIMESTAMP.sub("", line)
    # A group header carries no failure signal, but its text does ("Run pytest").
    line = _DIRECTIVE.sub("", line)
    # Progress bars rewrite one line with \r; keep only the final state.
    return line.rsplit("\r", 1)[-1].rstrip()


def isolate_error(state: DebugState) -> dict:
    """Strip noise, then keep windows around error markers."""
    lines = [_clean(ln) for ln in state.get("raw_log", "").splitlines()]

    hits = [i for i, ln in enumerate(lines) if any(m in ln for m in ERROR_MARKERS)]
    if not hits:
        # No anchor: the tail is the best guess.
        return {"error_region": "\n".join(lines[-LOG_LINES_AFTER:]), "log_markers": []}

    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - LOG_LINES_BEFORE), min(len(lines), i + LOG_LINES_AFTER + 1)))

    region, prev = [], None
    for i in sorted(keep):
        if prev is not None and i > prev + 1:
            region.append("...")
        region.append(lines[i])
        prev = i

    # Generic markers overlap specific ones: "Error:" matches inside the text
    # "ModuleNotFoundError:". When two matches overlap, keep the longer marker.
    hit_markers: set[str] = set()
    for i in hits:
        spans = [(lines[i].index(m), m) for m in ERROR_MARKERS if m in lines[i]]
        for at, m in spans:
            shadowed = any(
                o != m and at < oat + len(o) and oat < at + len(m) and len(o) > len(m)
                for oat, o in spans
            )
            if not shadowed:
                hit_markers.add(m)
    markers = sorted(hit_markers)
    return {"error_region": "\n".join(region), "log_markers": markers}
