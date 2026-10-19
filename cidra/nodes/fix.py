"""Fix generation and verification. See docs/4_architecture.md §5 nodes 12-15.

The safety-critical split: the LLM proposes text edits (data). CIDRA turns them
into a unified diff and decides the command (code). Nothing the model returns is
ever executed as a shell string.

verify_fix is the sole writer of `verified` — the one field the final report is
allowed to make a claim from.
"""

import builtins
import difflib
import pathlib
import re
import shlex
from typing import Optional

from pydantic import BaseModel, Field

from cidra import config, junit
from cidra.config import PRACTICE_REPO_DIR
from cidra.integrations.llm import structured
from cidra.nodes.environment import env_prefix, sandbox_install_command, sandbox_test_command, session_for
from cidra.nodes.reproduce import _same_test
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
- Large files are shown as excerpts. A line `# [cidra: N lines not shown]` marks
  a gap; never put it in `old`, and never span a gap with one edit.
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


_IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
# A repository file and line the log points at: "pkg/mod.py:12" or 'File "/work/pkg/mod.py", line 12'.
_LOG_LINE = re.compile(r"(?<![\w/.-])(?:/work/)?((?!/)[\w./-]+\.py)(?::|\", line )(\d+)")
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_NOT_DEFS = set(dir(builtins)) | {"self", "cls", "super", "print"}
WHOLE_FILE_CHARS = 12_000  # a file this small is shown whole
CONTEXT_CHARS = 48_000    # ponytail: one cap for every model; per-model limits if context windows differ
MAX_DEF_FILES = 4
SKIP = "# [cidra: {} lines not shown]"


def _read(root: pathlib.Path, path: str) -> Optional[str]:
    """A repository file's text, or None. `path` may come from the model or the
    log, so it must resolve inside the checkout (SR-03)."""
    target = (root / path).resolve()
    if not target.is_file() or not target.is_relative_to(root):
        return None
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _block_end(lines: list[str], start: int) -> int:
    """The line after the def or class that starts at `start`."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
        end += 1
    return end


def _defs(lines: list[str], names: set[str]) -> list[tuple[int, int]]:
    """Where each of `names` is defined in this file, as (first line, end) spans."""
    if not names:
        return []
    pattern = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(" + "|".join(map(re.escape, names)) + r")\b")
    return [(i, _block_end(lines, i)) for i, line in enumerate(lines) if pattern.match(line)]


def _excerpt(text: str, spans: list[tuple[int, int]]) -> str:
    """The whole file if small, else only `spans` (line ranges), each gap marked."""
    if len(text) <= WHOLE_FILE_CHARS:
        return text
    lines = text.splitlines(keepends=True)
    merged: list[list[int]] = []
    for start, end in sorted((max(0, s), min(len(lines), e)) for s, e in spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out, at = [], 0
    for start, end in merged:
        if start > at:
            out.append(SKIP.format(start - at) + "\n")
        out += lines[start:end]
        at = end
    if at < len(lines):
        out.append(SKIP.format(len(lines) - at) + "\n")
    return "".join(out)


def _context(state: DebugState) -> str:
    """What the model sees: the error, the failing test, and the code it reaches.

    Read from the run's checkout on the host, never through the sandbox's
    output tail, which cut every file to its last 16 KB. The diagnosis rarely
    names the file to fix, and an assertion's traceback stops in the test, so
    follow the failing test like a developer would: show the definitions of
    what it calls, wherever they live, plus the lines the log points at. Small
    files are shown whole; large ones as excerpts.
    """
    root = pathlib.Path(state.get("source_dir") or PRACTICE_REPO_DIR).resolve()
    analysis = state.get("analysis")
    region = state.get("error_region", "")

    files: dict[str, list[tuple[int, int]]] = {}  # path -> line spans worth showing
    if analysis and analysis.file:
        files[analysis.file] = []
    called: set[str] = set()
    failing = (analysis.failing_test if analysis else None) or ""
    test_file = failing.split("::")[0]
    test_text = _read(root, test_file) if test_file else None
    if test_text is not None:
        lines = test_text.splitlines()
        name = failing.split("::")[-1].split("[")[0]
        spans = _defs(lines, {name})
        files[test_file] = [(0, 30), *spans]  # its imports and the failing test
        for start, end in spans:
            called |= set(_CALL.findall("\n".join(lines[start:end])))
        called = {n for n in called - _NOT_DEFS if not n.startswith(("assert", "test"))}
        for module in _IMPORT.findall(test_text):
            base = module.replace(".", "/")
            files.setdefault(base + ".py" if _read(root, base + ".py") is not None else base + "/__init__.py", [])
    for path, line in _LOG_LINE.findall(region):
        files.setdefault(path, []).append((int(line) - 20, int(line) + 20))
    if called:
        hits = []
        for source in root.rglob("*.py"):
            rel = source.relative_to(root)
            if rel.as_posix() == test_file or {"test", "tests"} & set(rel.parts):
                continue
            lines = (_read(root, rel.as_posix()) or "").splitlines()
            spans = _defs(lines, called)
            if spans:
                # One hop further: what those definitions call, defined in the same file.
                inner = {n for s, e in spans for n in _CALL.findall("\n".join(lines[s:e]))} - _NOT_DEFS - called
                hits.append((len(spans), rel.as_posix(), spans + _defs(lines, inner)))
        for _, name, spans in sorted(hits, key=lambda h: (-h[0], h[1]))[:MAX_DEF_FILES]:
            files.setdefault(name, []).extend((s - 3, min(e, s + 150)) for s, e in spans)
    files.setdefault("requirements.txt", [])

    parts = [f"<error>\n{region}\n</error>"]
    if state.get("failure_detail"):
        parts.append(f"<failing_test_output>\n{state['failure_detail']}\n</failing_test_output>")
    # SBFL evidence (Phase 8): a mathematical suspiciousness ranking, so the model
    # edits where the spectrum points rather than the first file it happens to see.
    if state.get("sbfl_evidence"):
        parts.append(state["sbfl_evidence"])
    used = sum(map(len, parts))
    for path, spans in files.items():
        text = _read(root, path)
        if text is None or (len(text) > WHOLE_FILE_CHARS and not spans):
            continue
        shown = _excerpt(text, spans)
        if used + len(shown) > CONTEXT_CHARS:
            continue  # ponytail: drops whole files past the cap; trim spans if that loses the fix
        used += len(shown)
        parts.append(f"<file path=\"{path}\">\n{shown}</file>")
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


DETAIL_CHARS = 8_000
HEAD_CHARS = 1_500
_DIFF_MARKERS = ("Differing items", "Full diff", "Left contains", "Right contains", "At index")


def _failure_detail(state: DebugState) -> Optional[str]:
    """The target tests rerun alone with -vv, once per run.

    Without -vv pytest cuts an assertion's diff short ("use -vv to get more
    diff"): on the BugsInPy run the model saw that a value differed but not how,
    and gave up. Only a run where pytest ran and tests failed (exit 1) counts.
    """
    session = session_for(state["run_id"])
    wanted = state.get("target_tests") or []
    # The sandbox's own ids: the CI's may carry a different rootdir prefix.
    targets = [t for t in state.get("repro_failing_tests") or [] if any(_same_test(w, t) for w in wanted)][:5]
    if session is None or not targets:
        return None
    # Test ids come from the log: quoted, so they are arguments, never shell syntax (SR-03).
    run = session.run("test", env_prefix(state) + "python -m pytest -vv -p no:cacheprovider -p no:warnings "
                      + " ".join(map(shlex.quote, targets)) + " 2>&1")
    if run.exit_code != 1 or not run.stdout_tail.strip():
        return None
    # From the failures section on: the assertion and its diff come first there.
    out = run.stdout_tail
    header = out.find("= FAILURES =")
    out = out[out.rfind("\n", 0, header) + 1 if header >= 0 else 0:]
    # pytest prints both whole values before saying how they differ; for a large
    # dict that alone can fill the budget. Keep the test's code, then the diff.
    found = [i for i in (out.find(m) for m in _DIFF_MARKERS) if i >= 0]
    if found and min(found) > HEAD_CHARS:
        cut = out.rfind("\n", 0, min(found)) + 1
        out = out[:HEAD_CHARS] + f"\n[cidra: {cut - HEAD_CHARS} characters not shown]\n" + out[cut:]
    return out[:DETAIL_CHARS]


def generate_fix(state: DebugState) -> dict:
    attempts = state.get("fix_attempts", 0) + 1
    out: dict = {"fix_attempts": attempts}
    if "failure_detail" not in state:
        out["failure_detail"] = _failure_detail(state)
        state = {**state, **out}
    previous = state.get("verify_results", [])
    retry_note = ""
    apply_error = state.get("apply_error")
    if state.get("patch_applied") is False and apply_error:
        # The last edits never applied: say so, or the model sends them again.
        retry_note = (
            "\n\nYour previous edits could not be applied. Do not repeat them. Copy each "
            "old text exactly from the <file> contents above, with enough lines to be unique.\n"
        )
        if previous_diff := state.get("fix_diff"):
            retry_note += f"<previous_diff>\n{previous_diff[-2000:]}\n</previous_diff>\n"
        retry_note += f"<apply_error>\n{apply_error[-1000:]}\n</apply_error>"
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
        return {**out, "fix_diff": None, "analysis_error": str(e)[:500]}
    try:
        diff = edits_to_diff(patch.edits, pathlib.Path(state.get("source_dir") or PRACTICE_REPO_DIR))
    except ValueError as e:
        return {**out, "fix_diff": None, "patch_applied": False, "apply_error": str(e)}
    return {**out, "fix_diff": diff or None}


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
    after = junit.read(session)  # per-test results with the patch applied
    results.append(verified_run)
    verified, still_failing, regressions, note = judge_verification(state, verified_run, after)

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
        "verify_junit": after,
    }


def judge_verification(state: DebugState, run, report: dict[str, str] | None = None
                       ) -> tuple[bool, list[str], list[str], str | None]:
    """(verified, still failing, regressions, why not) for the run after the patch.

    Verified means the CI's failing tests no longer fail and nothing fails that
    did not fail before the patch. Tests that were already failing for another
    reason may stay red: they no longer make a real fix unverifiable, and they
    are reported. The failures come from the run's JUnit report, which lists
    every test, else from the log's FAILED lines (G-25). The run must complete
    normally (exit 0, or exit 1 with its failures); anything else proves nothing.
    """
    # ponytail: a target test the patch stops collecting would read as passing;
    # the audit gate refuses deleted tests, and G-22 covers edits to their setup.
    from cidra.nodes.reproduce import _same_test

    if run.passed:
        return True, [], [], None
    after = [] if run.timed_out or run.exit_code != 1 else junit.failures(report, run.stdout_tail + "\n" + run.stderr_tail)
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
