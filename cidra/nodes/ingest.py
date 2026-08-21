"""Log ingestion. See docs/4_architecture.md §5 nodes 1-2.

isolate_error is pure — the free/instant Tier 1 eval surface (docs/5_fixtures.md §6).
"""

import re

from cidra.config import ERROR_MARKERS, LOG_LINES_AFTER, LOG_LINES_BEFORE
from cidra.state import DebugState

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
# GitHub Actions prefixes every line with an ISO timestamp.
_TIMESTAMP = re.compile(r"^\S*\d{4}-\d{2}-\d{2}T[\d:.]+Z?\s?")


def fetch_log(state: DebugState) -> dict:
    """Phase 2: pull from GitHub. Until then raw_log is supplied by the fixture."""
    return {}


def _clean(line: str) -> str:
    line = _ANSI.sub("", line)
    line = _TIMESTAMP.sub("", line)
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
