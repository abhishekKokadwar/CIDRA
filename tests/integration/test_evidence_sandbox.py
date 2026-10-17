"""The evidence block from a real run: real sandbox, real nodes, real JUnit
reports (ROADMAP M2). Needs Docker and the sandbox image (CI builds both)."""

import pytest

from cidra.nodes.environment import close_session, prepare_sandbox, session_for
from cidra.nodes.fix import verify_fix
from cidra.nodes.publish import compose_report
from cidra.nodes.report import render_comment
from cidra.nodes.reproduce import reproduce_once
from cidra.sandbox.runner import client
from cidra.state import Analysis

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon, no image: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M2-EVIDENCE")

FIX = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n"
       "-    return a - b\n+    return a + b\n")


def test_a_verified_fix_report_shows_what_ran_and_each_test_before_and_after(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_zero():\n    assert add(0, 0) == 0\n")
    state = {"run_id": "it-evidence", "source_dir": str(tmp_path), "commit_sha": "feedface" * 5,
             "test_command": "python -m pytest -q 2>&1", "ci_failing_tests": ["tests/test_calc.py::test_add"],
             "analysis": Analysis(category="assertion_error", confidence=0.9, evidence="e", proposed_action="p")}
    try:
        state.update(prepare_sandbox(state))
        state.update(reproduce_once(state))
        assert session_for("it-evidence").apply_patch(FIX).passed
        state.update({"fix_diff": FIX, "patch_applied": True, "patch_audit_ok": True})
        state.update(verify_fix(state))
    finally:
        close_session("it-evidence")
    assert state["verified"]
    body = render_comment({**state, **compose_report(state)})
    assert "<b>Evidence</b>" in body
    assert "`feedfacefeed`" in body and "@sha256:" in body  # the exact image
    assert "python -m pytest -q 2>&1" in body and "| Audit gate | passed |" in body
    assert "| `tests.test_calc::test_add` (target) | failed | passed |" in body
    assert "| 1 other tests, unchanged | 1 passed | same |" in body
