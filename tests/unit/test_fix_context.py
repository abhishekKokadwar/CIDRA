"""The fix prompt must show the model the code it has to change, and a retry must
say why the last attempt failed. Found by the real-model runs: the source was
read through the sandbox's 16 KB output tail, so in 0 of 12 BugsInPy bugs the
lines the reference fix changes were in view."""

from cidra.nodes import fix
from cidra.state import Analysis

FILLER = "".join(f"def unrelated_{i}():\n    return {i}\n\n\n" for i in range(800))  # well past 16 KB
BIG = (
    FILLER
    + "def running_total(values):\n    return _accumulate(values[:-1])\n\n\n"
    + FILLER.replace("unrelated_", "more_")
    + "def _accumulate(values):\n    out, total = [], 0\n    for v in values:\n"
      "        total += v\n        out.append(total)\n    return out\n"
    + FILLER.replace("unrelated_", "tail_")
)
FILES = {
    "tests/test_calc.py": "from src.calc import running_total\nimport os\n\n\n"
                          "def test_running_total():\n    assert running_total([1, 2]) == [1, 3]\n",
    "src/calc.py": BIG,
    "src/small.py": "LIMIT = 3\n",
    "requirements.txt": "pytest\n",
}


def _state(root, **extra):
    analysis = Analysis(category="assertion_error", confidence=0.9, evidence="e",
                        proposed_action="p", failing_test="tests/test_calc.py::test_running_total")
    return {"run_id": "r", "source_dir": str(root), "analysis": analysis,
            "error_region": "tests/test_calc.py:6: AssertionError\nsrc/small.py:1\n/usr/lib/python3/x.py:4",
            **extra}


def _repo(tmp_path):
    for path, text in FILES.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    return tmp_path


def test_context_follows_the_failing_test_into_a_large_file(tmp_path):
    context = fix._context(_state(_repo(tmp_path)))  # the diagnosis names no file
    assert '<file path="src/calc.py">' in context
    assert "return _accumulate(values[:-1])" in context  # what the test calls
    assert "total += v" in context  # one call further, in the same file
    assert "def tail_799" not in context and "lines not shown]" in context  # an excerpt, not the tail
    assert '<file path="tests/test_calc.py">' in context and '<file path="src/small.py">' in context
    assert len(context) < fix.CONTEXT_CHARS + 2000


def test_context_never_reads_outside_the_checkout(tmp_path):
    root = _repo(tmp_path / "repo")
    (tmp_path / "secret.py").write_text("TOKEN = 'x'\n", encoding="utf-8")
    state = _state(root, error_region="../secret.py:1\n/usr/lib/python3/os.py:1")
    state["analysis"] = state["analysis"].model_copy(update={"file": "../secret.py"})
    context = fix._context(state)
    assert "TOKEN" not in context and '<file path="/usr' not in context


def test_retry_tells_the_model_its_edits_did_not_apply(tmp_path, monkeypatch):
    seen = {}

    def fake_structured(**kwargs):
        seen["user"] = kwargs["user"]
        return fix.Patch(edits=[], rationale="r")

    monkeypatch.setattr(fix, "structured", fake_structured)
    out = fix.generate_fix(_state(_repo(tmp_path), fix_attempts=1, fix_diff="OLD-DIFF", patch_applied=False,
                                  apply_error="error: patch failed: src/calc.py:8"))
    assert out["fix_attempts"] == 2
    assert "could not be applied" in seen["user"] and "OLD-DIFF" in seen["user"]
    assert "patch failed: src/calc.py:8" in seen["user"]
