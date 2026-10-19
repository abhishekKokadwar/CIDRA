"""The evidence block of every report (ROADMAP M2): what was run, on what, and
what each test did before and after the patch, so a reviewer can check a fix
from the pull request alone.

Pure: built from named state fields. Test ids and diff lines come from the
repository, so they are cleaned before they go into a Markdown table.
"""

import re
import shlex

from cidra.junit import junit_id
from cidra.state import DebugState

MAX_ROWS = 25
_DEPENDENCY_FILE = re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.py|setup\.cfg)$")


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


def test_changes(state: DebugState) -> tuple[list[dict], dict[str, int]]:
    """(shown, rest): targets first, then every test whose outcome changed, then
    tests already failing, each {test, before, after, note}; and the count per
    outcome of the unchanged rest. The report's table and the dashboard read this."""
    before, after = state.get("repro_junit") or {}, state.get("verify_junit") or {}
    if not before:
        return [], {}
    targets = [junit_id(t) for t in state.get("target_tests") or []]
    changed = [t for t in sorted(before.keys() | after.keys()) if after and before.get(t) != after.get(t)]
    already = [t for t in sorted(before) if before[t] in ("failed", "error")]
    shown = []
    for t in dict.fromkeys([*targets, *changed, *already]):
        b, a = before.get(t, "absent"), after.get(t, "not run") if after else "not run"
        note = "target" if t in targets else "now failing" if b == "passed" and a in ("failed", "error") else ""
        shown.append({"test": t, "before": b, "after": a, "note": note})
    rest = [t for t in before if t not in {r["test"] for r in shown}]
    counts = {o: n for o in ("passed", "skipped", "failed", "error") if (n := sum(before[t] == o for t in rest))}
    return shown, counts


def test_rows(state: DebugState) -> list[str]:
    """test_changes() as the report's Markdown table."""
    shown, rest = test_changes(state)
    if not shown and not rest:
        return []
    rows = ["| Test | Before | After |", "|---|---|---|"]
    for r in shown[:MAX_ROWS]:
        note = {"target": " (target)", "now failing": " **(now failing)**"}.get(r["note"], "")
        rows.append(f"| `{_cell(r['test'])}`{note} | {r['before']} | {r['after']} |")
    if len(shown) > MAX_ROWS:
        rows.append(f"| … {len(shown) - MAX_ROWS} more | | |")
    if rest:
        rows.append(f"| {sum(rest.values())} other tests, unchanged | "
                    + ", ".join(f"{n} {o}" for o, n in rest.items()) + " | same |")
    return rows


def rerun_command(state: DebugState) -> str:
    """`cidra verify` with this run's commit, commands and targets. Every part is
    shell-quoted: test ids and commands come from the repository, and a reviewer
    will paste this into a terminal."""
    from cidra import config
    from cidra.nodes.environment import sandbox_install_command
    parts = ["cidra", "verify", "--sha", state.get("commit_sha") or "HEAD", "--patch", "fix.diff",
             "--install", sandbox_install_command(state),
             "--test", state.get("test_command") or config.TEST_COMMAND]
    for target in state.get("target_tests") or []:
        parts += ["--target", target]
    return " ".join(shlex.quote(p) for p in parts)


def render(state: DebugState) -> list[str]:
    """The block as Markdown lines, or [] when no sandbox ran."""
    if not state.get("image_tag"):
        return []
    from cidra import config
    from cidra.integrations.llm import run_cost, usage_summary
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
        cost = run_cost()
        facts.append(("Model", f"`{_cell(config.MODEL_FIX)}`, {used['requests']} requests, "
                               f"{used['prompt_tokens']:,} prompt + {used['completion_tokens']:,} completion tokens"
                               + (f", about ${cost[0]:.4f} at {cost[1]}" if cost else "")))

    lines = ["", "<details><summary><b>Evidence</b>: what was run and what each test did</summary>", "",
             "| | |", "|---|---|", *(f"| {k} | {v} |" for k, v in facts)]
    rows = test_rows(state)
    if rows:
        lines += ["", "Tests before → after the patch:", "", *rows]
    if state.get("fix_diff"):
        lines += ["", "Rerun this verification in your own sandbox (`fix.diff` is this pull request's diff, "
                      "e.g. `gh pr diff <number> > fix.diff`):", "",
                  "```sh", rerun_command(state).replace("```", "'''"), "```"]
    return lines + ["", "</details>"]
