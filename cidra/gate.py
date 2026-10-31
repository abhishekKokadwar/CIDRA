"""The gate on its own (ROADMAP M8): judge a diff, whoever wrote it, with no model.

check() runs the same steps the repair pipeline runs after a patch exists, using
the same node functions: the audit, reproduction of the failure, the patch on a
clean copy, and verification. `cidra verify` and the check-PR Action mode call
it; the pipeline's graph calls those nodes one by one.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

VERIFIED, REFUSED, NOT_VERIFIED, NOT_REPRODUCED, ERROR = "verified", "refused", "not_verified", "not_reproduced", "error"

_HEADLINES = {
    VERIFIED: "✅ **Verified by CIDRA**: the failure was reproduced, this diff makes the failing tests pass, "
              "and no test that passed now fails.",
    REFUSED: "⛔ **Refused by CIDRA's audit gate**: this diff was not run.",
    NOT_VERIFIED: "❌ **Not verified by CIDRA**: the diff applies, but the tests say it does not fix the failure.",
    NOT_REPRODUCED: "⚠️ **Not checked**: CIDRA could not reproduce the failure, so there is nothing to verify against.",
    ERROR: "⚠️ **Not checked**: CIDRA could not run the check.",
}


@dataclass
class Verdict:
    outcome: str
    reason: str = ""
    state: Any = field(default_factory=dict)  # a DebugState, built up as the check runs

    @property
    def verified(self) -> bool:
        return self.outcome == VERIFIED

    def markdown(self) -> str:
        """A PR comment or job summary: the verdict, why, and the evidence block."""
        from cidra.evidence import render
        lines = [_HEADLINES[self.outcome]]
        if self.outcome == REFUSED:
            lines += ["", *(f"- {r}" for r in self.state.get("patch_audit_reasons") or [])]
        elif self.reason and not self.verified:
            lines += ["", self.reason]
        return "\n".join(lines + render(self.state))


def check(source: str, sha: str, diff: str, targets: list[str],
          install: Optional[str] = None, test: Optional[str] = None) -> Verdict:
    """Judge `diff` against the failing commit `sha` of the repository at `source`.
    `targets` are the tests that must go from failing to passing."""
    from cidra.nodes.audit import audit_patch
    from cidra.nodes.checkout import prepare_checkout, remove_checkout
    from cidra.nodes.environment import close_session, install_deps, prepare_sandbox, session_for, workflow_python
    from cidra.nodes.fix import verify_fix
    from cidra.nodes.reproduce import reproduce_once

    run_id = f"verify-{uuid.uuid4().hex[:8]}"
    state: Any = {"run_id": run_id, "install_command": install, "test_command": test,
                  "ci_failing_tests": targets, "commit_sha": sha, "fix_diff": diff}
    try:
        tree = prepare_checkout(run_id, source, sha)
        state.update(source_dir=str(tree), python_version=workflow_python(tree))
        # Before any sandbox work: a refused diff is never run, whatever wrote it.
        state.update(audit_patch(state))
        if not state.get("patch_audit_ok"):
            return Verdict(REFUSED, "; ".join(state.get("patch_audit_reasons") or []), state)
        state.update(prepare_sandbox(state))
        if state.get("env_ready") is not False:
            state.update(install_deps(state))
        if state.get("env_ready") is False:
            return Verdict(ERROR, f"Could not set up the sandbox: {state.get('analysis_error')}", state)
        state.update(reproduce_once(state))
        if not state.get("reproduced"):
            return Verdict(NOT_REPRODUCED, f"Not reproduced, so there is nothing to verify: {state.get('analysis_error')}", state)
        session = session_for(run_id)
        if session is None:
            return Verdict(ERROR, "The sandbox session closed before the patch could be applied.", state)
        applied = session.apply_patch(diff)
        if not applied.passed:
            return Verdict(NOT_VERIFIED, f"The patch does not apply to {sha}:\n"
                                         f"{(applied.stdout_tail or applied.stderr_tail)[-1000:]}", state)
        state.update(verify_fix({**state, "patch_applied": True}))
    except Exception as e:  # noqa: BLE001 - no Docker, no image, not a git repo
        return Verdict(ERROR, f"Could not run the verification: {e}", state)
    finally:
        close_session(run_id)
        remove_checkout(run_id)
    if state.get("verified"):
        return Verdict(VERIFIED, "", state)
    return Verdict(NOT_VERIFIED, f"Not verified: {state.get('verify_note')}", state)
