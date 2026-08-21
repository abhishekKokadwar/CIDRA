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
STRATEGIES = {
    "missing_dependency": "append_requirement",
    "assertion_error": "patch_source",
    "env_config_error": "patch_workflow",
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
    """Deterministic dispatch on category. No LLM call."""
    analysis = state.get("analysis")
    if analysis is None:
        return {}
    return {"fix_strategy": STRATEGIES.get(analysis.category)}


def _context(state: DebugState) -> str:
    """What the model sees: the error region plus the files it may edit."""
    session = session_for(state["run_id"])
    analysis = state.get("analysis")
    wanted = [f for f in (analysis.file if analysis else None, "requirements.txt") if f]
    if state.get("fix_strategy") == "patch_workflow" and state.get("workflow_file"):
        wanted.append(state["workflow_file"])

    parts = [f"<error>\n{state.get('error_region', '')}\n</error>"]
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
    return {
        "verified": verified_run.passed,
        "verify_results": [*state.get("verify_results", []), *results],
    }
