"""Fix generation and verification. See docs/4_architecture.md §5 nodes 12-15.

The safety-critical split: the LLM proposes text edits (data). CIDRA turns them
into a unified diff and decides the command (code). Nothing the model returns is
ever executed as a shell string.

verify_fix is the sole writer of `verified` — the one field the final report is
allowed to make a claim from.
"""

import difflib
import pathlib
import re
import shlex
from typing import Optional

from pydantic import BaseModel, Field

from cidra import config
from cidra.config import PRACTICE_REPO_DIR
from cidra.integrations.llm import structured
from cidra.nodes.environment import sandbox_install_command, sandbox_test_command, session_for
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


class Edit(BaseModel):
    path: str = Field(description="File to change, relative to the repository root, as in <file path=...>.")
    old: str = Field(description="Exact text to replace, copied from the file with its indentation. "
                                 "Include enough lines that it appears only once. Empty to add "
                                 "text at the end of the file, or to create a new file.")
    new: str = Field(description="The text that replaces `old`.")


class Patch(BaseModel):
    """LLM output for a fix. Text edits, never a command or a hand-written diff:
    models get diff line counts and context wrong, so CIDRA builds the diff."""

    edits: list[Edit] = Field(default_factory=list, description="Empty if you cannot fix it.")
    rationale: str


SYSTEM = """You repair a single CI failure by proposing text edits to the files shown.

Hard rules:
- Output edits only. Never shell commands, never instructions to run anything.
- Change the minimum needed to make the failing test pass. No refactors, no
  cleanups, no unrelated edits, no new files unless the fix is impossible without one.
- Never edit a test to make it pass when the code under test is wrong. Fixing the
  symptom by weakening the check is a failed repair, not a repair.
- Each edit's `old` text must be copied exactly from the <file> contents shown,
  and must appear in that file only once.
- If you cannot fix it from the evidence given, return no edits rather than
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


_PY_PATH = re.compile(r"[\w./-]+\.py")
_IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
MAX_CONTEXT_FILES = 6


def _candidate_files(state: DebugState, session) -> list[str]:
    """Files worth showing the model, most relevant first.

    The diagnosis often names no file (the analysis prompt forbids guessing one),
    and a model that cannot see the source invents it and writes a diff that
    cannot apply. So also take the failing test, the modules that test imports,
    and any relative .py path the log names. Paths that do not exist in the
    sandbox simply fail to `cat` and are dropped by the caller.
    """
    analysis = state.get("analysis")
    found: list[str] = []
    if analysis and analysis.file:
        found.append(analysis.file)
    test_file = None
    if analysis and analysis.failing_test:
        test_file = analysis.failing_test.split("::")[0]
        found.append(test_file)
        if session is not None:
            shown = session.run("test", f"cat -- {shlex.quote(test_file)}", timeout_s=30)
            if shown.passed:
                found += [m.replace(".", "/") + ".py" for m in _IMPORT.findall(shown.stdout_tail)]
    found += [p for p in _PY_PATH.findall(state.get("error_region", "")) if not p.startswith("/")]
    files = list(dict.fromkeys(found))[:MAX_CONTEXT_FILES]
    return [*files, "requirements.txt"]


def _context(state: DebugState) -> str:
    """What the model sees: the error region plus the files it may edit."""
    session = session_for(state["run_id"])
    analysis = state.get("analysis")
    wanted = _candidate_files(state, session)

    parts = [f"<error>\n{state.get('error_region', '')}\n</error>"]
    # SBFL evidence (Phase 8): a mathematical suspiciousness ranking, so the model
    # edits where the spectrum points rather than the first file it happens to see.
    evidence = state.get("sbfl_evidence")
    if evidence:
        parts.append(evidence)
    for path in dict.fromkeys(wanted):
        if session is None:
            break
        # `path` can come from the model (analysis.file): quote it so it is an
        # argument to cat, never shell syntax (SR-03).
        shown = session.run("test", f"cat -- {shlex.quote(path)}", timeout_s=30)
        if shown.passed:
            parts.append(f"<file path=\"{path}\">\n{shown.stdout_tail}</file>")
    if analysis is not None:
        parts.append(f"<diagnosis>\n{analysis.model_dump_json(indent=2)}\n</diagnosis>")
    return "\n\n".join(parts)


def _unified(path: str, before: Optional[str], after: str) -> str:
    lines = difflib.unified_diff(before.splitlines(keepends=True) if before else [],
                                 after.splitlines(keepends=True),
                                 "/dev/null" if before is None else f"a/{path}", f"b/{path}")
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                   for line in lines)


def edits_to_diff(edits: list[Edit], root: pathlib.Path) -> str:
    """The model's edits as one unified diff against `root`, the run's checkout.

    Raises ValueError, worded for the model, when an edit cannot be placed: a path
    outside the checkout, or an `old` text that is missing or not unique.
    """
    root = root.resolve()
    before: dict[str, Optional[str]] = {}
    after: dict[str, str] = {}
    for n, edit in enumerate(edits, 1):
        # The path comes from the model: it must stay inside the checkout (SR-03).
        target = (root / edit.path).resolve()
        if target == root or not target.is_relative_to(root):
            raise ValueError(f"edit {n}: {edit.path!r} is not a file in the repository")
        path = target.relative_to(root).as_posix()
        if path not in after:
            try:
                before[path] = None
                if target.is_file():
                    with target.open(encoding="utf-8", newline="") as f:  # keep CRLF as is
                        before[path] = f.read()
            except (OSError, UnicodeDecodeError) as e:
                raise ValueError(f"edit {n}: cannot read {path}: {e}") from e
            after[path] = before[path] or ""
        text, old, new = after[path], edit.old, edit.new
        if "\r\n" in text:  # the model writes \n; match the file's line endings
            old, new = (s.replace("\r\n", "\n").replace("\n", "\r\n") for s in (old, new))
        if not old:
            after[path] = text + ("\n" if text and not text.endswith("\n") else "") + new
            continue
        count = text.count(old)
        if count != 1:
            where = "was not found in" if count == 0 else f"appears {count} times in"
            raise ValueError(f"edit {n}: the old text {where} {path}:\n{edit.old[:500]}")
        after[path] = text.replace(old, new)
    return "".join(_unified(p, before[p], after[p]) for p in after if after[p] != (before[p] or ""))


def generate_fix(state: DebugState) -> dict:
    attempts = state.get("fix_attempts", 0) + 1
    previous = state.get("verify_results", [])
    retry_note = ""
    if state.get("patch_applied") is False and state.get("apply_error"):
        # The last edits never applied: say so, or the model sends them again.
        retry_note = (
            "\n\nYour previous edits could not be applied. Do not repeat them. Copy each "
            "old text exactly from the <file> contents above, with enough lines to be unique.\n"
        )
        if state.get("fix_diff"):
            retry_note += f"<previous_diff>\n{state['fix_diff'][-2000:]}\n</previous_diff>\n"
        retry_note += f"<apply_error>\n{state['apply_error'][-1000:]}\n</apply_error>"
    elif previous:
        last = previous[-1]
        retry_note = (
            "\n\nA previous attempt did not work. Do not repeat it.\n"
            f"<previous_attempt_output>\n{last.stdout_tail[-2000:]}\n</previous_attempt_output>"
        )
        if state.get("verify_note"):
            retry_note += f"\n<why_it_failed>\n{state['verify_note']}\n</why_it_failed>"
    try:
        patch = structured(
            model=config.MODEL_FIX,  # read at call time: the settings API can change it
            schema=Patch,
            system=SYSTEM,
            user=_context(state) + retry_note,
            max_tokens=4000,  # edits quote the old text, so they run longer than a diff
        )
    except Exception as e:
        return {"fix_attempts": attempts, "fix_diff": None, "analysis_error": str(e)[:500]}
    try:
        diff = edits_to_diff(patch.edits, pathlib.Path(state.get("source_dir") or PRACTICE_REPO_DIR))
    except ValueError as e:
        return {"fix_attempts": attempts, "fix_diff": None, "patch_applied": False, "apply_error": str(e)}
    return {"fix_attempts": attempts, "fix_diff": diff or None}


def apply_patch(state: DebugState) -> dict:
    """Apply the diff as data. `git apply` refuses anything malformed."""
    session = session_for(state["run_id"])
    diff = state.get("fix_diff")
    if session is None or not diff:
        return {"patch_applied": False}
    result = session.apply_patch(diff)
    error = None if result.passed else (result.stdout_tail or result.stderr_tail).strip()[-1000:]
    return {"patch_applied": result.passed, "apply_error": error}


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
        results.append(session.install(sandbox_install_command(state)))
        if not results[-1].passed:
            return {"verified": False, "verify_results": [*state.get("verify_results", []), *results]}

    verified_run = session.run("verify", sandbox_test_command(state))
    results.append(verified_run)
    verified, still_failing, regressions, note = judge_verification(state, verified_run)

    # Phase 11: cache a freshly verified fix (only on a genuine verify, and not
    # when the diff itself came from the cache — nothing new to learn). This is
    # the sole cache writer, so only proven-green diffs are ever stored.
    if verified and not state.get("cache_hit"):
        fp = state.get("fingerprint")
        diff = state.get("fix_diff")
        if fp and diff:
            from cidra.nodes import fix_cache
            analysis = state.get("analysis")
            fix_cache.put(fp, diff, analysis.category if analysis else "unknown",
                          meta={"run_id": state.get("run_id", "")})

    return {
        "verified": verified,
        "verify_results": [*state.get("verify_results", []), *results],
        "verify_failing_tests": still_failing,
        "regressions": regressions,
        "verify_note": note,
    }


def judge_verification(state: DebugState, run) -> tuple[bool, list[str], list[str], str | None]:
    """(verified, still failing, regressions, why not) for the run after the patch.

    Verified means the CI's failing tests no longer fail and nothing fails that
    did not fail before the patch. Tests that were already failing for another
    reason may stay red: they no longer make a real fix unverifiable, and they
    are reported. Only failures are listed in pytest's output, so the run must
    complete normally (exit 0, or exit 1 with its failure list); anything else
    proves nothing.
    """
    # ponytail: a target test the patch stops collecting would read as passing;
    # the audit gate refuses deleted tests, and G-22 covers edits to their setup.
    from cidra.nodes.ingest import failing_tests
    from cidra.nodes.reproduce import _same_test

    if run.passed:
        return True, [], [], None
    after = [] if run.timed_out or run.exit_code != 1 else failing_tests(run.stdout_tail + "\n" + run.stderr_tail)
    if not after:
        why = "timed out" if run.timed_out else f"exit {run.exit_code}"
        return False, [], [], f"the test run after the patch did not complete normally ({why})"
    targets = state.get("target_tests") or []
    before = state.get("repro_failing_tests") or []
    still_red = [t for t in targets if any(_same_test(t, a) for a in after)]
    regressions = [a for a in after if not any(_same_test(a, b) for b in before)]
    if not targets:
        return False, after, regressions, "no target test is known, so only a fully green run verifies"
    if still_red:
        return False, after, regressions, f"still failing after the patch: {', '.join(still_red[:5])}"
    if regressions:
        return False, after, regressions, f"the patch broke tests that passed before: {', '.join(regressions[:5])}"
    return True, after, [], None
