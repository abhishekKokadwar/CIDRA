"""The evidence block of every report (ROADMAP M2): what was run, on what, and
what each test did before and after the patch, so a reviewer can check a fix
from the pull request alone.

Pure: built from named state fields. Test ids and diff lines come from the
repository, so they are cleaned before they go into a Markdown table.
"""

import re

from cidra.state import DebugState

MAX_ROWS = 25
_DEPENDENCY_FILE = re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.py|setup\.cfg)$")


def junit_id(nodeid: str) -> str:
    """A pytest node id in the form the JUnit report uses (cidra/junit.py):
    "tests/test_a.py::TestX::test_y[p]" -> "tests.test_a.TestX::test_y[p]"."""
    path, _, rest = nodeid.partition("::")
    parts = rest.split("::")
    module = path.removesuffix(".py").replace("/", ".")
    return f"{'.'.join([module, *parts[:-1]])}::{parts[-1]}" if rest else module


def _cell(text: object) -> str:
    """Repository text as a table cell: no pipe, backtick or newline can escape it."""
    return re.sub(r"[|`\s]+", " ", str(text)).strip()[:200]


def dependency_changes(diff: str | None) -> list[str]:
    """Lines the patch adds to a dependency file, as "file: line"."""
    out, path = [], None
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip().removeprefix("b/")
        elif path and _DEPENDENCY_FILE.search(path) and line.startswith("+") and line[1:].strip():
            out.append(f"{path}: {line[1:].strip()}")
    return out


def test_rows(state: DebugState) -> list[str]:
    """The before/after table: targets first, then every test whose outcome
    changed, then tests already failing; the unchanged rest as one count."""
    before, after = state.get("repro_junit") or {}, state.get("verify_junit") or {}
    if not before:
        return []
    targets = [junit_id(t) for t in state.get("target_tests") or []]
    changed = [t for t in sorted(before.keys() | after.keys()) if after and before.get(t) != after.get(t)]
    already = [t for t in sorted(before) if before[t] in ("failed", "error")]
    shown = list(dict.fromkeys([*targets, *changed, *already]))
    rows = ["| Test | Before | After |", "|---|---|---|"]
    for t in shown[:MAX_ROWS]:
        b, a = before.get(t, "absent"), after.get(t, "not run") if after else "not run"
        note = " (target)" if t in targets else " **(now failing)**" if b == "passed" and a in ("failed", "error") else ""
        rows.append(f"| `{_cell(t)}`{note} | {b} | {a} |")
    if len(shown) > MAX_ROWS:
        rows.append(f"| … {len(shown) - MAX_ROWS} more | | |")
    rest = [t for t in before if t not in shown]
    if rest:
        counts = {o: sum(before[t] == o for t in rest) for o in ("passed", "skipped", "failed", "error")}
        rows.append(f"| {len(rest)} other tests, unchanged | "
                    + ", ".join(f"{n} {o}" for o, n in counts.items() if n) + " | same |")
    return rows


def render(state: DebugState) -> list[str]:
    """The block as Markdown lines, or [] when no sandbox ran."""
    if not state.get("image_tag"):
        return []
    from cidra import config
    from cidra.integrations.llm import usage_summary
    from cidra.nodes.environment import sandbox_install_command, sandbox_test_command

    python = state.get("python_version") or "the image default"
    facts = [
        ("Failing commit", f"`{_cell(state.get('commit_sha', '?'))[:12]}` (the patch is made against it)"),
        ("Sandbox", f"`{_cell(state['image_tag'])}`, Python {_cell(python)}, no network while tests run"),
        ("Install command", f"`{_cell(sandbox_install_command(state))}`"),
        ("Test command", f"`{_cell(sandbox_test_command(state))}`"),
    ]
    if state.get("patch_audit_ok") is not None:
        reasons = state.get("patch_audit_reasons") or []
        facts.append(("Audit gate", "passed" if state["patch_audit_ok"] else "refused: " + "; ".join(map(_cell, reasons[:3]))))
    deps = dependency_changes(state.get("fix_diff"))
    if state.get("fix_diff"):
        facts.append(("Dependency change", "; ".join(f"`{_cell(d)}`" for d in deps[:10]) if deps else "none"))
    used = usage_summary()
    if used["requests"]:
        facts.append(("Model", f"`{_cell(config.MODEL_FIX)}`, {used['requests']} requests, "
                               f"{used['prompt_tokens']:,} prompt + {used['completion_tokens']:,} completion tokens"))

    lines = ["", "<details><summary><b>Evidence</b>: what was run and what each test did</summary>", "",
             "| | |", "|---|---|", *(f"| {k} | {v} |" for k, v in facts)]
    rows = test_rows(state)
    if rows:
        lines += ["", "Tests before → after the patch:", "", *rows]
    return lines + ["", "</details>"]
