"""Render a DebugState into an honest Markdown comment body. Phase 6, step 6.1.

Pure: no I/O, no network. The GitHub write path (github_write.py) takes the
string this produces and posts it. Kept separate so the composition rules —
which are the SR-12 boundary — are unit-testable without a token.

Two hard rules, both from docs/threat/security_requirements.md:
  - SR-12: the body is assembled from NAMED state fields. Model-authored prose
    (analysis.evidence, proposed_action) appears only inside a labelled,
    length-capped block, never rendered as if it were CIDRA's own statement.
  - The §7 invariant: never present an unverified change as a fix. Only
    outcome == "verified_fix" gets the fix diff and the "verified green" claim.
"""

from cidra.state import DebugState

# Model prose is untrusted data. Cap it so an injected 1 MB "explanation"
# cannot bloat or dominate the comment (SEC-01 residual channel).
MAX_PROSE = 600
MAX_DIFF = 8000

_MARKER = "<!-- cidra:report -->"  # lets github_write find & update its own comment


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n… (truncated)"


def _model_block(state: DebugState) -> str:
    """Model-authored prose, fenced and labelled as such. Never bare."""
    a = state.get("analysis")
    if a is None:
        return ""
    body = _clip(getattr(a, "evidence", ""), MAX_PROSE)
    action = _clip(getattr(a, "proposed_action", ""), MAX_PROSE)
    lines = ["> _Model-generated analysis (untrusted; shown for the reviewer):_", ">"]
    if body:
        lines += [f"> {ln}" for ln in body.splitlines()]
    if action:
        lines += [">", "> **Proposed action:**"] + [f"> {ln}" for ln in action.splitlines()]
    return "\n".join(lines)


def _category(state: DebugState) -> str:
    a = state.get("analysis")
    return a.category if a is not None else "unknown"


def render_comment(state: DebugState) -> str:
    """The comment body. `compose_report` must have set `outcome` first."""
    outcome = state.get("outcome", "failed")
    cat = _category(state)
    head = {
        "verified_fix": "✅ **CIDRA — verified fix**",
        "flaky_detected": "🎲 **CIDRA — flaky test detected**",
        "diagnosis_only": "🔎 **CIDRA — diagnosis only** (no verified fix)",
        "failed": "⚠️ **CIDRA — could not diagnose**",
    }.get(outcome, "⚠️ **CIDRA**")

    parts = [_MARKER, head, "", f"**Failure class:** `{cat}`"]

    if outcome == "verified_fix":
        diff = _clip(state.get("fix_diff"), MAX_DIFF)
        parts += [
            "",
            "This patch was applied in a network-isolated sandbox and the test "
            "suite passed. It is a **suggestion** — review before merging.",
            "",
            "```diff",
            diff,
            "```",
        ]
        surfaced = state.get("patch_surfaced") or []
        if surfaced:
            # SR-14: dependency changes are called out, never folded silently into the diff.
            parts += ["", "⚠️ **Dependency change — review explicitly:**"]
            parts += [f"- {s}" for s in surfaced[:10]]
    elif outcome == "flaky_detected":
        passes = state.get("flaky_pass_count")
        runs = len(state.get("repro_results", [])) or None
        score = state.get("flaky_score")
        detail = f" ({passes}/{runs} runs passed)" if passes is not None and runs else ""
        score_line = f" Flakiness score **{score}/100**." if score is not None else ""
        parts += [
            "",
            f"The failing test is **intermittent**{detail}.{score_line} No fix was "
            "attempted — a flaky test is not repaired by patching the code it flutters on.",
        ]
    elif outcome == "diagnosis_only":
        rejects = state.get("patch_audit_reasons") or []
        if rejects:
            # A patch WAS generated but the static policy checks rejected it (Phase 10).
            # Say so plainly — this is the moat feature earning its keep.
            parts += [
                "",
                "CIDRA generated a candidate fix but **rejected it** on static policy "
                "checks — it would have cheated the test suite or weakened the repo:",
                "",
            ]
            parts += [f"- {r}" for r in rejects[:10]]
        else:
            parts += [
                "",
                "CIDRA classified the failure but did **not** produce a fix it could "
                "verify green. No change is suggested. See the analysis below.",
            ]
    else:  # failed
        err = state.get("analysis_error")
        parts += ["", "CIDRA could not produce a usable diagnosis for this run."]
        if err:
            parts += ["", f"_Reason:_ `{_clip(err, 200)}`"]

    block = _model_block(state)
    if block:
        parts += ["", block]

    parts += ["", "---", "_CIDRA never merges. A human approves every change._"]
    return "\n".join(parts)
