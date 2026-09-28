"""Fix generation and verification. See docs/4_architecture.md §5 nodes 12-15.

The safety-critical split: the LLM produces a unified diff (data). CIDRA decides
the command (code). Nothing the model returns is ever executed as a shell string.

verify_fix is the sole writer of `verified` — the one field the final report is
allowed to make a claim from.
"""

from typing import Optional

from pydantic import BaseModel, Field

from cidra.config import MODEL_FIX, TEST_COMMAND
from cidra.integrations.llm import structured
from cidra.nodes.environment import session_for
from cidra.state import DebugState

# Which file each category is allowed to touch. Deterministic, no LLM.
# See docs/4_architecture.md §5.1.
#
# env_config_error has no entry on purpose: the fix would edit
# .github/workflows/ci.yml, but the sandbox invokes pytest directly and never
# reads that file, so verify_fix could never actually confirm the patch
# worked. Leaving it out routes straight to diagnosis_only (0 LLM calls)
# instead of "verifying" against a sandbox that can't see the change.
STRATEGIES = {
    "missing_dependency": "append_requirement",
    "assertion_error": "patch_source",
}


class Patch(BaseModel):
    """LLM output for a fix. A diff, never a command."""

    diff: str = Field(description="Unified diff with a/ and b/ prefixes.")
    target_file: str
    rationale: str


SYSTEM = """You repair a single CI failure by emitting one unified diff.

Hard rules:
- Output a diff only. Never shell commands, never instructions to run anything.
- Change the minimum needed to make the failing test pass. No refactors, no
  cleanups, no unrelated edits, no new files unless the fix is impossible without one.
- Never edit a test to make it pass when the code under test is wrong. Fixing the
  symptom by weakening the check is a failed repair, not a repair.
- The diff must apply with `git apply` against the paths shown. Include correct
  @@ hunk headers and full context lines.
- If you cannot fix it from the evidence given, emit an empty diff rather than
  guessing. An honest non-fix beats a plausible wrong one."""


def select_strategy(state: DebugState) -> dict:
    """Deterministic dispatch on category, plus a fix-cache check. No LLM call.

    Phase 11: if this exact failure (by fingerprint) has a previously VERIFIED
    fix cached, reuse its diff and skip generate_fix (the LLM). The patch is
    still audited (SR-13/14) and re-verified in the sandbox — the cache saves the
    model call, never the verification, so a stale cached diff can't yield a false
    `verified`.
    """
    from cidra.nodes.fingerprint import fingerprint
    from cidra.nodes import fix_cache

    analysis = state.get("analysis")
    if analysis is None:
        return {}

    out: dict = {"fix_strategy": STRATEGIES.get(analysis.category)}
    fp = fingerprint(state.get("error_region", ""))
    if fp:
        out["fingerprint"] = fp
        cached = fix_cache.get(fp)
        if cached and cached.get("diff"):
            out["fix_diff"] = cached["diff"]
            out["cache_hit"] = True
    return out


def _context(state: DebugState) -> str:
    """What the model sees: the error region plus the files it may edit."""
    session = session_for(state["run_id"])
    analysis = state.get("analysis")
    wanted = [f for f in (analysis.file if analysis else None, "requirements.txt") if f]

    parts = [f"<error>\n{state.get('error_region', '')}\n</error>"]
    # SBFL evidence (Phase 8): a mathematical suspiciousness ranking, so the model
    # edits where the spectrum points rather than the first file it happens to see.
    evidence = state.get("sbfl_evidence")
    if evidence:
        parts.append(evidence)
    for path in dict.fromkeys(wanted):
        if session is None:
            break
        shown = session.run("test", f"cat {path}", timeout_s=30)
        if shown.passed:
            parts.append(f"<file path=\"{path}\">\n{shown.stdout_tail}</file>")
    if analysis is not None:
        parts.append(f"<diagnosis>\n{analysis.model_dump_json(indent=2)}\n</diagnosis>")
    return "\n\n".join(parts)


def generate_fix(state: DebugState) -> dict:
    attempts = state.get("fix_attempts", 0) + 1
    previous = state.get("verify_results", [])
    retry_note = ""
    if previous:
        last = previous[-1]
        retry_note = (
            "\n\nA previous attempt did not work. Do not repeat it.\n"
            f"<previous_attempt_output>\n{last.stdout_tail[-2000:]}\n</previous_attempt_output>"
        )
    try:
        patch = structured(
            model=MODEL_FIX,
            schema=Patch,
            system=SYSTEM,
            user=_context(state) + retry_note,
            max_tokens=2000,
        )
    except Exception as e:
        return {"fix_attempts": attempts, "fix_diff": None, "analysis_error": str(e)[:500]}
    return {"fix_attempts": attempts, "fix_diff": patch.diff or None}


def apply_patch(state: DebugState) -> dict:
    """Apply the diff as data. `git apply` refuses anything malformed."""
    session = session_for(state["run_id"])
    diff = state.get("fix_diff")
    if session is None or not diff:
        return {"patch_applied": False}
    result = session.apply_patch(diff)
    return {"patch_applied": result.passed}


def verify_fix(state: DebugState) -> dict:
    """Sole writer of `verified`. See docs/4_architecture.md §3.1.

    Reinstalls first: a dependency fix changes requirements.txt, and a green run
    against the old environment would prove nothing.
    """
    session = session_for(state["run_id"])
    if session is None or not state.get("patch_applied"):
        return {"verified": False}

    results = []
    if state.get("fix_strategy") == "append_requirement":
        results.append(session.install("pip install --quiet -r requirements.txt"))
        if not results[-1].passed:
            return {"verified": False, "verify_results": [*state.get("verify_results", []), *results]}

    env = state.get("ci_env") or {}
    prefix = "".join(f"{k}={v} " for k, v in sorted(env.items()))
    verified_run = session.run("verify", prefix + TEST_COMMAND)
    results.append(verified_run)

    # Phase 11: cache a freshly verified fix (only on a genuine verify, and not
    # when the diff itself came from the cache — nothing new to learn). This is
    # the sole cache writer, so only proven-green diffs are ever stored.
    if verified_run.passed and not state.get("cache_hit"):
        fp = state.get("fingerprint")
        diff = state.get("fix_diff")
        if fp and diff:
            from cidra.nodes import fix_cache
            analysis = state.get("analysis")
            fix_cache.put(fp, diff, analysis.category if analysis else "unknown",
                          meta={"run_id": state.get("run_id", "")})

    return {
        "verified": verified_run.passed,
        "verify_results": [*state.get("verify_results", []), *results],
    }
