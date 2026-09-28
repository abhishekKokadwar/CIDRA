"""AST-level static policy checks on a proposed patch. Phase 10.

The enterprise moat (docs/3_phases.md §10): CIDRA statically proves a generated
diff does not cheat the test suite or weaken security *before* it ever runs in
the sandbox. A patch that passes the tests by deleting the assertion is a failed
repair, not a repair — and the sandbox alone cannot tell the difference, because
the deleted-assertion version really is green.

Implements SR-13 / SR-14 / SR-15 from docs/threat/security_requirements.md, and
is exercised by eval/security_fixtures/07_repo_write_abuse (SEC-07).

No LLM. Pure parsing of the unified diff the model already produced:
  - SR-13  reject deleting/skipping/weakening tests
  - SR-14  reject touching CI/agent config; SURFACE dependency-pin changes
  - SR-15  reject an oversized patch (line/file ceiling)

The verdict is data on the state; the router turns a rejection into a
diagnosis-only outcome so nothing unsafe reaches apply_patch.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from cidra.state import DebugState

# --- SR-15 ceilings. A CIDRA fix class is narrow; a sprawling diff is off-scope. ---
MAX_CHANGED_LINES = 200
MAX_CHANGED_FILES = 10

# --- SR-14 forbidden paths: config CIDRA must never rewrite. ---
_FORBIDDEN_PATHS = (
    ".github/",            # workflows, actions
    ".cidra/",             # CIDRA's own config
    "AGENTS.md",
    "CLAUDE.md",
)
_CI_YAML = re.compile(r"\.github/workflows/.*\.ya?ml$")

# --- SR-14 pin files whose changes must be SURFACED, not silently applied. ---
_DEP_FILES = ("requirements.txt", "requirements.in", "setup.py", "setup.cfg",
              "pyproject.toml", "Pipfile", "poetry.lock")

# --- SR-13 markers that weaken/skip a test even without deleting it. ---
_SKIP_MARKERS = ("@pytest.mark.skip", "@pytest.mark.xfail", "pytest.skip(",
                 "unittest.skip", "@unittest.skip", "@skip")


@dataclass
class FileDiff:
    path: str          # the b/ (new) path, or a/ path for a deletion
    old_path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    is_deletion: bool = False


@dataclass
class AuditVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)     # why rejected (SR-13/14/15)
    surfaced: list[str] = field(default_factory=list)    # pin changes to show the reviewer


def _parse_diff(diff: str) -> list[FileDiff]:
    """Split a unified diff into per-file added/removed content lines.

    Deliberately small: we only need the +/- payload lines and the file paths,
    not a full patch model. Hunk headers and context lines are ignored.
    """
    files: list[FileDiff] = []
    cur: Optional[FileDiff] = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            old = line[4:].strip()
            cur = FileDiff(path=old, old_path=old)
            continue
        if line.startswith("+++ "):
            if cur is None:
                cur = FileDiff(path="", old_path="")
            new = line[4:].strip()
            cur.path = _strip_prefix(new if new != "/dev/null" else cur.old_path)
            cur.old_path = _strip_prefix(cur.old_path)
            cur.is_deletion = new == "/dev/null"
            files.append(cur)
            continue
        if cur is None or line.startswith("@@") or line.startswith("diff "):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            cur.added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            cur.removed.append(line[1:])
    return files


def _strip_prefix(path: str) -> str:
    for p in ("a/", "b/"):
        if path.startswith(p):
            return path[len(p):]
    return path


def _is_test_path(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in f"/{path}"


def _removed_assertions(removed: list[str]) -> int:
    """Count assert statements in removed lines, robustly.

    Parse the removed block as Python; fall back to a line regex if the fragment
    doesn't parse on its own (removed hunks often aren't valid standalone code).
    """
    src = "\n".join(removed)
    try:
        tree = ast.parse(src)
        return sum(isinstance(n, ast.Assert) for n in ast.walk(tree))
    except SyntaxError:
        return sum(1 for ln in removed if re.match(r"\s*assert\b", ln))


def audit_diff(diff: str) -> AuditVerdict:
    """Static policy verdict for a unified diff. No side effects, no LLM."""
    if not diff or not diff.strip():
        # An empty diff is an honest non-fix, not a violation — let it route on.
        return AuditVerdict(ok=True)

    files = _parse_diff(diff)
    reasons: list[str] = []
    surfaced: list[str] = []

    total_changed = sum(len(f.added) + len(f.removed) for f in files)
    if len(files) > MAX_CHANGED_FILES:
        reasons.append(f"SR-15: patch touches {len(files)} files (max {MAX_CHANGED_FILES})")
    if total_changed > MAX_CHANGED_LINES:
        reasons.append(f"SR-15: patch changes {total_changed} lines (max {MAX_CHANGED_LINES})")

    for f in files:
        # SR-14 — forbidden config paths.
        if _CI_YAML.search(f.path) or any(f.path.startswith(p) or f.path == p.rstrip("/")
                                          for p in _FORBIDDEN_PATHS):
            reasons.append(f"SR-14: patch touches protected path '{f.path}'")

        # SR-13 — deleting or gutting a test.
        if _is_test_path(f.path):
            removes_test_def = any(re.match(r"\s*def test", ln) for ln in f.removed)
            adds_test_def = any(re.match(r"\s*def test", ln) for ln in f.added)
            if f.is_deletion or (removes_test_def and not adds_test_def):
                reasons.append(f"SR-13: patch deletes test(s) in '{f.path}'")
            else:
                removed_asserts = _removed_assertions(f.removed)
                added_asserts = _removed_assertions(f.added)  # reuse counter on added
                if removed_asserts > added_asserts:
                    reasons.append(
                        f"SR-13: patch removes {removed_asserts - added_asserts} "
                        f"assertion(s) from '{f.path}'")
            if any(m in ln for ln in f.added for m in _SKIP_MARKERS):
                reasons.append(f"SR-13: patch skips/xfails a test in '{f.path}'")

        # SR-13 — weakening a conditional to a constant-true (if True:).
        for ln in f.added:
            if re.match(r"\s*(if|while)\s+True\s*:", ln):
                reasons.append(f"SR-13: patch weakens a conditional to always-true in '{f.path}'")
            if re.search(r"verify\s*=\s*False", ln):
                reasons.append(f"SR-13: patch disables TLS/verification in '{f.path}'")

        # SR-14 — dependency-pin changes must be surfaced, not silently applied.
        if any(f.path == d or f.path.endswith("/" + d) for d in _DEP_FILES):
            if f.added or f.removed:
                surfaced.append(f"dependency change in '{f.path}': "
                                f"-{len(f.removed)}/+{len(f.added)} line(s) — review the package/version")

    # Dedup while preserving order.
    reasons = list(dict.fromkeys(reasons))
    surfaced = list(dict.fromkeys(surfaced))
    return AuditVerdict(ok=not reasons, reasons=reasons, surfaced=surfaced)


def audit_patch(state: DebugState) -> dict:
    """Graph node: gate the LLM's diff before it reaches the sandbox.

    Writes `patch_audit_ok` (drives routing) and `patch_audit_reasons`. A
    rejected patch never reaches apply_patch — the router sends it to the report,
    where it becomes diagnosis_only (an honest "no safe fix found").
    """
    verdict = audit_diff(state.get("fix_diff") or "")
    out: dict = {
        "patch_audit_ok": verdict.ok,
        "patch_audit_reasons": verdict.reasons,
    }
    if verdict.surfaced:
        out["patch_surfaced"] = verdict.surfaced
    return out
