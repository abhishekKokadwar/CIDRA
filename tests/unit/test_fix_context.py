"""The fix prompt must show the model the real source, and a retry must say why
the last diff failed. Both were found by the first real-model run."""

from cidra.nodes import fix
from cidra.state import Analysis, SandboxResult

FILES = {
    "tests/test_calc.py": "from src.calc import running_total\nimport os\n\ndef test_running_total(): ...\n",
    "src/calc.py": "def running_total(values):\n    for v in values[:-1]:\n        ...\n",
    "requirements.txt": "pytest\n",
}


class FakeSession:
    def run(self, step, command, timeout_s=None):
        path = command.removeprefix("cat -- ").strip("'")
        ok = path in FILES
        return SandboxResult(step="test", exit_code=0 if ok else 1, stdout_tail=FILES.get(path, ""),
                             stderr_tail="", duration_s=0.0, timed_out=False)


def _state(**extra):
    analysis = Analysis(category="assertion_error", confidence=0.9, evidence="e",
                        proposed_action="p", failing_test="tests/test_calc.py::test_running_total")
    return {"run_id": "r", "analysis": analysis,
            "error_region": "tests/test_calc.py:13: AssertionError\n/usr/lib/python3/x.py", **extra}


def test_context_includes_the_source_the_failing_test_imports(monkeypatch):
    monkeypatch.setattr(fix, "session_for", lambda _run_id: FakeSession())
    context = fix._context(_state())  # the diagnosis names no file
    assert '<file path="src/calc.py">' in context and "values[:-1]" in context
    assert '<file path="tests/test_calc.py">' in context
    assert '<file path="os.py">' not in context and '<file path="/usr' not in context  # absent files are dropped


def test_retry_tells_the_model_its_diff_did_not_apply(monkeypatch):
    monkeypatch.setattr(fix, "session_for", lambda _run_id: FakeSession())
    seen = {}

    def fake_structured(**kwargs):
        seen["user"] = kwargs["user"]
        return fix.Patch(diff="d2", target_file="src/calc.py", rationale="r")

    monkeypatch.setattr(fix, "structured", fake_structured)
    out = fix.generate_fix(_state(fix_attempts=1, fix_diff="OLD-DIFF", patch_applied=False,
                                  apply_error="error: patch failed: src/calc.py:8"))
    assert out["fix_attempts"] == 2
    assert "did not apply" in seen["user"] and "OLD-DIFF" in seen["user"]
    assert "patch failed: src/calc.py:8" in seen["user"]
