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


def _fence(text: str | None, limit: int) -> list[str]:
    """Untrusted output (an install log, a runner error) in a code block it cannot close."""
    return ["```", _clip(text, limit).replace("```", "'''"), "```"]


def _why_failed(state: DebugState) -> tuple[str, list[str]]:
    """Title and body for a run that ended `failed`: which step stopped it, and
    which input to change (G-18). These are the usual first-run failures on a
    new repository, so "could not diagnose" alone sent people to the source."""
    from cidra import config
    err = state.get("analysis_error")
    last = (state.get("repro_results") or [None])[-1]
    if state.get("env_ready") is False and last is not None and last.step == "install" and not last.passed:
        from cidra.nodes.environment import sandbox_install_command
        cmd = sandbox_install_command(state)
        return "⚠️ **CIDRA — could not install the dependencies**", [
            "", f"The sandbox could not install the project with `{cmd}`, so CIDRA did not try to "
                "reproduce or fix the failure.", "", "_Install output:_", *_fence(err, 600), "",
            "If the project installs another way, set the `install_command` input: one `pip install` "
            "command (CIDRA appends `--target`).",
        ]
    if state.get("env_ready") and state.get("analysis") is not None and not state.get("reproduced"):
        cmd = state.get("test_command") or config.TEST_COMMAND
        lines = ["", f"CIDRA diagnosed the failure but could not make it fail in the sandbox with `{cmd}`, "
                     "so it did not attempt a fix."]
        if err:
            lines += ["", "_Why:_", *_fence(err, 400)]
        return "⚠️ **CIDRA — diagnosed, but could not reproduce**", lines + [
            "", "If your CI runs the tests differently (another directory, extra options or environment), "
                "set the `test_command` input to match.",
        ]
    lines = ["", "CIDRA could not produce a usable diagnosis for this run."]
    if err:
        lines += ["", f"_Reason:_ `{_clip(err, 200)}`"]
    return "⚠️ **CIDRA — could not diagnose**", lines


def render_comment(state: DebugState) -> str:
    """The comment body. `compose_report` must have set `outcome` first."""
    outcome = state.get("outcome", "failed")
    cat = _category(state)
    failed_head, failed_body = _why_failed(state) if outcome == "failed" else ("", [])
    head = {
        "verified_fix": "✅ **CIDRA — verified fix**",
        "flaky_detected": "🎲 **CIDRA — flaky test detected**",
        "diagnosis_only": "🔎 **CIDRA — diagnosis only** (no verified fix)",
        "failed": failed_head,
    }.get(outcome, "⚠️ **CIDRA**")

    parts = [_MARKER, head, "", f"**Failure class:** `{cat}`"]

    if outcome == "verified_fix":
        diff = _clip(state.get("fix_diff"), MAX_DIFF)
        parts += [
            "",
            "This patch was applied in a network-isolated sandbox: the failing "
            "tests now pass, and no test that passed before it fails. It is a "
            "**suggestion** — review before merging.",
            "",
            "```diff",
            diff,
            "```",
        ]
        already = state.get("verify_failing_tests") or []
        if already:
            # Not caused by the patch: they failed the same way before it.
            parts += ["", "These tests were already failing before the patch and still fail:"]
            parts += [f"- `{t}`" for t in already[:10]]
        surfaced = state.get("patch_surfaced") or []
        if surfaced:
            # SR-14: dependency changes are called out, never folded silently into the diff.
            parts += ["", "⚠️ **Dependency change — review explicitly:**"]
            parts += [f"- {s}" for s in surfaced[:10]]
    elif outcome == "flaky_detected":
        passes = state.get("flaky_pass_count")
        # The dependency install is recorded alongside the test runs; it is not one.
        runs = sum(getattr(r, "step", "test") == "test" for r in state.get("repro_results", [])) or None
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
            if state.get("verify_note"):
                parts += ["", f"_Last attempt:_ {_clip(state['verify_note'], 300)}"]
    else:  # failed
        parts += failed_body

    from cidra.evidence import render as evidence
    parts += evidence(state)  # ROADMAP M2: what was run, and each test before and after

    block = _model_block(state)
    if block:
        parts += ["", block]

    manifest = state.get("audit_manifest")
    if manifest and manifest.get("seal"):
        pol_dec = manifest.get("policy", {}).get("decision", "auto_remediate").upper()
        ast_status = "PASSED" if manifest.get("security", {}).get("ast_audit_passed") else "BLOCKED"
        sig_hex = manifest["seal"].get("signature", "")[:16]
        seal_line = (f"`HMAC-SHA256:{sig_hex}…`" if sig_hex
                     else "unsigned (set `CIDRA_AUDIT_SIGNING_KEY` to sign)")
        parts += [
            "",
            "🔒 **Enterprise Audit Manifest:**",
            f"- **Policy Decision:** `{pol_dec}`",
            f"- **AST Security Gate:** `{ast_status}`",
            f"- **Sandbox Isolation:** `0 egress bytes` (network disabled)",
            f"- **Cryptographic Seal:** {seal_line}",
        ]

    parts += ["", "---", "_CIDRA never merges. A human approves every change._"]
    return "\n".join(parts)
