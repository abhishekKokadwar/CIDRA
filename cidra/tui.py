"""Fleet TUI — a terminal view over CIDRA run history. Phase 13 (offline part).

Reads the run-history store (history.py) and prints a table of recent runs:
what failed, how it was resolved, whether a cached fix was reused, and where the
comment/PR landed. Stdlib only — no curses, no `rich`/`textual` dependency — so
it renders in any terminal and needs nothing installed.

    python -m cidra.tui              # last 20 runs
    python -m cidra.tui --limit 50
    python -m cidra.tui --watch      # refresh every 2s (Ctrl-C to stop)

The live container/token-spend view and the web dashboard are deferred
(docs/KNOWN_GAPS.md); this is the read-only history view.
"""

import argparse
import time

from cidra import history

# outcome -> a short glyph + label, so the table scans at a glance.
_OUTCOME = {
    "verified_fix": "[OK ] verified",
    "flaky_detected": "[FLK] flaky",
    "diagnosis_only": "[DX ] diagnosis",
    "failed": "[ERR] failed",
}


def _fmt_ts(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except (TypeError, ValueError, OSError):
        return "?"


def _row(r: dict) -> list[str]:
    extra = []
    if r.get("cache_hit"):
        extra.append("cached")
    if r.get("flaky_score") is not None and r.get("outcome") == "flaky_detected":
        extra.append(f"score {r['flaky_score']}")
    if r.get("pr_url"):
        extra.append("PR")
    elif r.get("comment_url"):
        extra.append("comment")
    return [
        _fmt_ts(r.get("ts")),
        (r.get("repo") or "")[:28],
        (r.get("commit_sha") or "")[:10],
        _OUTCOME.get(r.get("outcome", ""), r.get("outcome", "?")),
        (r.get("category") or "-")[:18],
        ", ".join(extra),
    ]


_HEADERS = ["when", "repo", "commit", "outcome", "class", "notes"]


def render(rows: list[dict]) -> str:
    """The history table as a string. Empty history says so."""
    if not rows:
        return "No CIDRA runs recorded yet."
    table = [_HEADERS] + [_row(r) for r in rows]
    widths = [max(len(row[c]) for row in table) for c in range(len(_HEADERS))]
    out = []
    for i, row in enumerate(table):
        out.append("  ".join(cell.ljust(widths[c]) for c, cell in enumerate(row)))
        if i == 0:
            out.append("  ".join("-" * w for w in widths))
    n = len(rows)
    ok = sum(r.get("outcome") == "verified_fix" for r in rows)
    cached = sum(1 for r in rows if r.get("cache_hit"))
    out.append("")
    out.append(f"{n} run(s) · {ok} verified · {cached} served from cache")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CIDRA Fleet TUI — run history")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--watch", action="store_true", help="refresh every 2s")
    args = ap.parse_args(argv)

    if not args.watch:
        print(render(history.load(limit=args.limit)))
        return 0
    try:
        while True:
            print("\033[2J\033[H", end="")  # clear + home
            print("CIDRA Fleet — live (Ctrl-C to stop)\n")
            print(render(history.load(limit=args.limit)))
            time.sleep(2)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
