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
import pathlib
import re
from dataclasses import dataclass, field
from typing import Optional

from cidra.policy import ContainmentLimits
from cidra.state import DebugState

# --- SR-15 ceilings. A CIDRA fix class is narrow; a sprawling diff is off-scope.
# One source of truth: the policy's containment_limits. These are its defaults,
# used when no policy is passed to audit_diff. ---
MAX_CHANGED_LINES = ContainmentLimits().max_changed_lines
MAX_CHANGED_FILES = ContainmentLimits().max_changed_files

# --- SR-14 forbidden paths: config CIDRA must never rewrite. ---
_FORBIDDEN_PATHS = (
    ".github/",            # workflows, actions
    ".cidra/",             # CIDRA's own config
    "cidra.policy.yml",    # Enterprise policy specification
    "AGENTS.md",
    "CLAUDE.md",
)
_CI_YAML = re.compile(r"\.github/workflows/.*\.ya?ml$")

# --- SR-14 pin files whose changes must be SURFACED, not silently applied. ---
_DEP_FILES = ("requirements.txt", "requirements.in", "setup.py", "setup.cfg",
              "pyproject.toml", "Pipfile", "poetry.lock")

# --- SR-13 markers that weaken/skip a test even without deleting it. ---
_SKIP_MARKERS = (
    "@pytest.mark.skip", "@pytest.mark.skipif", "@pytest.mark.xfail",
    "pytest.skip(", "pytest.xfail(",
    "unittest.skip", "@unittest.skip", "@skip", "unittest.case.skip",
    "self.skipTest(", "raise unittest.SkipTest", "@unittest.expectedFailure",
    "__test__ = False", "__test__=False",
    "test.skip(", "describe.skip(", "it.skip(", "test.todo("
)


@dataclass
class FileDiff:
    path: str          # the b/ (new) path, or a/ path for a deletion
    old_path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    is_deletion: bool = False
    is_new: bool = False


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
            cur.is_new = cur.old_path == "/dev/null"
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
    return base.startswith("test_") or base.endswith("_test.py") or base.endswith(".test.ts") or base.endswith(".spec.ts") or base.endswith(".test.js") or base.endswith(".spec.js") or "/tests/" in f"/{path}"


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
        return sum(1 for ln in removed if re.match(r"\s*(assert|expect)\b", ln))


_NO_LITERAL = object()
_MISSING_MODULE = re.compile(r"No module named ['\"]([A-Za-z_]\w*)")
_IF_EQUALS = re.compile(r"\s*(?:el)?if\s+(.+?)\s*==\s*(.+?)\s*:\s*(?:return\s+(.+))?$")
_RETURN = re.compile(r"\s*return\s+(.+)$")


def _literal(src: str):
    """The Python literal `src` spells, or _NO_LITERAL."""
    try:
        return ast.literal_eval(src.strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return _NO_LITERAL


def call_expectations(source: str) -> list[tuple[tuple, object]]:
    """(call arguments, expected value) for each `f(<literals>) == <literal>` in a test file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    pairs = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)):
            continue
        for call, other in ((node.left, node.comparators[0]), (node.comparators[0], node.left)):
            if not isinstance(call, ast.Call) or call.keywords:
                continue
            args = tuple(_literal(ast.unparse(a)) for a in call.args)
            expected = _literal(ast.unparse(other))
            if args and expected is not _NO_LITERAL and _NO_LITERAL not in args:
                pairs.append((args, expected))
    return pairs


def _matches_input(value, args: tuple) -> bool:
    if len(args) == 1:
        return value == args[0]
    return isinstance(value, (tuple, list)) and tuple(value) == args


def _hardcoded_answers(added: list[str], expectations) -> bool:
    """True when the patch adds `if <input> == <a test's input>: return <that test's answer>`."""
    # ponytail: only the literal-equality form is caught, and a genuine base case
    # the failing test happens to assert (`if n == 0: return 1`) is refused too.
    # Refusing costs a diagnosis-only report; verifying a cheat costs trust.
    # An obfuscated special case (`if sum(values) == 6`) still gets through:
    # only held-out or generated tests can catch that.
    for i, ln in enumerate(added):
        m = _IF_EQUALS.match(ln)
        if not m:
            continue
        ret = m.group(3)
        if ret is None and i + 1 < len(added):
            nxt = _RETURN.match(added[i + 1])
            ret = nxt.group(1) if nxt else None
        if ret is None:
            continue
        answer = _literal(ret)
        inputs = [v for v in (_literal(m.group(1)), _literal(m.group(2))) if v is not _NO_LITERAL]
        if any(answer == expected and _matches_input(v, args)
               for args, expected in expectations for v in inputs):
            return True
    return False


def audit_diff(diff: str, limits: Optional[ContainmentLimits] = None,
               missing_modules: tuple = (), expectations: tuple = ()) -> AuditVerdict:
    """Static policy verdict for a unified diff. No side effects, no LLM.

    `limits` are the loaded policy's containment limits; defaults apply without them.
    `missing_modules` are the import names the failing run could not find, and
    `expectations` are the failing test's (arguments, expected value) pairs: with
    them the gate also refuses a patch that fakes the module or hardcodes the answer.
    """
    limits = limits or ContainmentLimits()
    if not diff or not diff.strip():
        # An empty diff is an honest non-fix, not a violation — let it route on.
        return AuditVerdict(ok=True)

    files = _parse_diff(diff)
    reasons: list[str] = []
    surfaced: list[str] = []

    total_changed = sum(len(f.added) + len(f.removed) for f in files)
    if len(files) > limits.max_changed_files:
        reasons.append(f"SR-15: patch touches {len(files)} files (max {limits.max_changed_files})")
    if total_changed > limits.max_changed_lines:
        reasons.append(f"SR-15: patch changes {total_changed} lines (max {limits.max_changed_lines})")

    for f in files:
        # SR-14 — forbidden config paths.
        if _CI_YAML.search(f.path) or any(f.path.startswith(p) or f.path == p.rstrip("/")
                                          for p in _FORBIDDEN_PATHS):
            reasons.append(f"SR-14: patch touches protected path '{f.path}'")

        # SR-13 — faking the missing dependency with a local module of the same name.
        parts = f.path.split("/")
        module = parts[-2] if parts[-1] == "__init__.py" and len(parts) > 1 else parts[-1].removesuffix(".py")
        if f.is_new and f.path.endswith(".py") and module in missing_modules:
            reasons.append(f"SR-13: patch adds '{f.path}', a stand-in for the missing module '{module}'")

        # SR-13 — returning the failing test's expected value for the failing test's input.
        if not _is_test_path(f.path) and expectations and _hardcoded_answers(f.added, expectations):
            reasons.append(f"SR-13: patch hardcodes the failing test's expected value in '{f.path}'")

        # SR-13 — deleting or gutting a test.
        if _is_test_path(f.path):
            removes_test_def = any(re.match(r"\s*(def test|it\(|test\()", ln) for ln in f.removed)
            adds_test_def = any(re.match(r"\s*(def test|it\(|test\()", ln) for ln in f.added)
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

        # SR-13 — Exception swallowing in test files across lines
        if _is_test_path(f.path):
            test_src = "\n".join(f.added)
            if re.search(r"\bexcept\s*(?:AssertionError|Exception|BaseException)?\s*:\s*(?:pass|\.\.\.|\n\s*(?:pass|\.\.\.))", test_src):
                reasons.append(f"SR-13: patch swallows assertions or exceptions in test '{f.path}'")

        # SR-13 — weakening a conditional to a constant-true (if True:).
        for ln in f.added:
            if re.match(r"\s*(if|while)\s+True\s*:", ln):
                reasons.append(f"SR-13: patch weakens a conditional to always-true in '{f.path}'")
            if re.search(r"\bassert\s+(True|False\s*==\s*False|1\s*==\s*1|0\s*==\s*0|not\s+False|\S+\s+or\s+True|\S+\s+or\s+1\b)", ln):
                reasons.append(f"SR-13: patch weakens assertion to constant-true in '{f.path}'")
            if re.search(r"\bself\.(?:assertTrue\s*\(\s*(?:True|1\s*==\s*1|0\s*==\s*0|False\s*==\s*False|not\s+False)|\bassertEqual\s*\(\s*(?:1\s*,\s*1|0\s*,\s*0|True\s*,\s*True|False\s*,\s*False))\b", ln):
                reasons.append(f"SR-13: patch weakens unittest assertion to constant-true in '{f.path}'")
            if _is_test_path(f.path):
                if re.search(r"\b(?:time|asyncio)\.sleep\s*\(", ln):
                    reasons.append(f"SR-13: patch injects sleep in test to mask timing race conditions in '{f.path}'")
            if re.search(r"verify\s*=\s*False", ln):
                reasons.append(f"SR-13: patch disables TLS/verification in '{f.path}'")
            # SR-13 / Security: Disallowed system / subprocess / network socket calls in patch
            if re.search(r"\bos\.(system|popen)\(", ln):
                reasons.append(f"SR-13: patch contains disallowed system execution (os.system/os.popen) in '{f.path}'")
            if re.search(r"\bsubprocess\.(Popen|run|call|check_output|check_call)\(", ln):
                reasons.append(f"SR-13: patch contains disallowed subprocess invocation in '{f.path}'")
            if re.search(r"\b(import\s+socket|from\s+socket\s+import|socket\.connect\b|socket\.socket\b)", ln):
                reasons.append(f"SR-13: patch contains disallowed socket/network operations in '{f.path}'")

            # SR-13 / Security Red Team Expanded Controls:
            # 1. Dynamic code evaluation (eval/exec)
            if re.search(r"\b(eval|exec)\s*\(", ln):
                reasons.append(f"SR-13: patch contains dynamic code evaluation (eval/exec) in '{f.path}'")
            # 2. Obfuscated reflection / import tricks
            if re.search(r"\b(__import__|__builtins__|importlib\.import_module)\b", ln):
                reasons.append(f"SR-13: patch contains disallowed dynamic reflection in '{f.path}'")
            # 3. Insecure deserialization
            if re.search(r"\b(pickle\.loads|yaml\.unsafe_load)\b", ln):
                reasons.append(f"SR-13: patch contains insecure object deserialization in '{f.path}'")
            # 4. Outbound network dials / DNS tunneling
            if re.search(r"\b(urllib\.request|socket\.gethostbyname|socket\.getaddrinfo|socket\.create_connection)\b", ln):
                reasons.append(f"SR-13: patch contains unauthorized network communication in '{f.path}'")
            # 5. Sensitive environment variable scraping
            if re.search(r"\bos\.environ(?:\.items|\.values|(?:\[|\.get\()\s*['\"](?:AWS_|GITHUB_|SECRET|TOKEN|KEY|PRIVATE_KEY))", ln):
                reasons.append(f"SR-13: patch attempts to harvest sensitive environment variables in '{f.path}'")
            # 6. File permission escalation
            if re.search(r"\bos\.chmod\([^,]+,\s*0o?[0-7]{3}\)", ln) and ("777" in ln or "666" in ln):
                reasons.append(f"SR-13: patch loosens file permissions in '{f.path}'")
            # 7. Signal handler tampering
            if re.search(r"\bsignal\.signal\s*\([^,]+,\s*signal\.SIG_IGN\)", ln):
                reasons.append(f"SR-13: patch manipulates signal handlers to suppress timeouts in '{f.path}'")
            # 8. Hardcoded secrets / private keys
            if re.search(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9]+)", ln):
                reasons.append(f"SR-13: patch introduces hardcoded private key or secret token in '{f.path}'")

        # Pytest hook manipulation or conftest tampering
        if f.path.endswith("conftest.py") or any(re.match(r"\s*def pytest_", ln) for ln in f.added):
            if any("pytest_runtest_" in ln or "pytest_sessionfinish" in ln for ln in f.added):
                reasons.append(f"SR-13: patch tampers with pytest internal runner hooks in '{f.path}'")

        # Test discovery / runner config tampering
        if f.path.endswith("pytest.ini") or f.path.endswith("tox.ini") or f.path == "setup.cfg" or f.path.endswith("pyproject.toml") or f.path.endswith("noxfile.py") or f.path.endswith("Makefile"):
            for ln in f.added:
                if re.search(r"(--ignore|--deselect|-k\b|maxfail|timeout\s*=|session\.skip|addopts\s*=.*--ignore)", ln):
                    reasons.append(f"SR-14: patch tampers with test discovery/timeout configuration in '{f.path}'")

        # Untrusted package index in dependency files
        if any(f.path == d or f.path.endswith("/" + d) for d in _DEP_FILES):
            for ln in f.added:
                if re.search(r"(--(extra-)?index-url|git\+https?://|https?://)", ln):
                    reasons.append(f"SR-14: patch injects untrusted external repository or index URL in '{f.path}'")

        # SR-14 — dependency-pin changes must be surfaced, not silently applied.
        if any(f.path == d or f.path.endswith("/" + d) for d in _DEP_FILES):
            if f.added or f.removed:
                surfaced.append(f"dependency change in '{f.path}': "
                                f"-{len(f.removed)}/+{len(f.added)} line(s) — review the package/version")

    # Dedup while preserving order.
    reasons = list(dict.fromkeys(reasons))
    surfaced = list(dict.fromkeys(surfaced))
    return AuditVerdict(ok=not reasons, reasons=reasons, surfaced=surfaced)


def _run_context(state: DebugState) -> tuple[tuple, tuple]:
    """What a cheat would look like for this run: the module names the log could
    not import, and what the failing test file asserts."""
    analysis = state.get("analysis")
    text = f"{getattr(analysis, 'evidence', '') or ''}\n{state.get('error_region') or ''}"
    missing = set(_MISSING_MODULE.findall(text))
    if getattr(analysis, "missing_package", None):
        missing.add(analysis.missing_package)

    expectations: list = []
    test_file = (getattr(analysis, "failing_test", None) or "").split("::")[0]
    if test_file and state.get("source_dir"):
        root = pathlib.Path(state["source_dir"]).resolve()
        path = (root / test_file).resolve()
        if path.is_file() and path.is_relative_to(root):
            expectations = call_expectations(path.read_text(encoding="utf-8", errors="replace"))
    return tuple(sorted(missing)), tuple(expectations)


def audit_patch(state: DebugState) -> dict:
    """Graph node: gate the LLM's diff before it reaches the sandbox.

    Enforces both AST static rules (SR-13/14/15) and Declarative Policy (cidra.policy.yml).
    A rejected patch never reaches apply_patch — the router sends it to the report,
    where it becomes diagnosis_only (an honest "no safe fix found").
    """
    diff = state.get("fix_diff") or ""

    from cidra.policy import PolicyEngine, PolicyDecision
    source_dir = state.get("source_dir")
    policy_engine = PolicyEngine.find_and_load(source_dir)
    verdict = audit_diff(diff, policy_engine.rule.containment, *_run_context(state))
    p_decision, p_reasons = policy_engine.evaluate_diff(diff)

    final_reasons = list(verdict.reasons)
    final_surfaced = list(verdict.surfaced)
    requires_human = state.get("requires_human_approval", False)

    if p_decision == PolicyDecision.STRICT_REFUSAL:
        final_reasons.extend([r for r in p_reasons if r != "Diff is empty"])
        patch_ok = False
    elif p_decision == PolicyDecision.REQUIRE_HUMAN_APPROVAL:
        requires_human = True
        final_surfaced.extend([r for r in p_reasons if r != "Diff is empty"])
        patch_ok = verdict.ok
    else:
        patch_ok = verdict.ok

    out: dict = {
        "patch_audit_ok": patch_ok,
        "patch_audit_reasons": list(dict.fromkeys(final_reasons)),
        "requires_human_approval": requires_human,
        "policy_decision": p_decision.value if p_decision != PolicyDecision.AUTO_REMEDIATE else state.get("policy_decision", "auto_remediate"),
    }
    if final_surfaced:
        out["patch_surfaced"] = list(dict.fromkeys(final_surfaced))
    return out
