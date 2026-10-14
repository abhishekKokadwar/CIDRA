"""A reproduction must show the failure the CI reported, not just any red run (KNOWN_GAPS G-17)."""

from pathlib import Path

from cidra.nodes import reproduce
from cidra.nodes.ingest import failing_tests, isolate_error
from cidra.state import Analysis, DebugState, SandboxResult

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def _red(*failed: str) -> SandboxResult:
    summary = "".join(f"FAILED {t} - AssertionError\n" for t in failed)
    return SandboxResult(step="test", exit_code=1, stdout_tail=f"{len(failed)} failed\n{summary}",
                         stderr_tail="", duration_s=0.1, timed_out=False)


class _Session:
    def __init__(self, result):
        self.result = result

    def run(self, step, command, timeout_s=None):
        return self.result


def _reproduce(monkeypatch, result, **state):
    monkeypatch.setattr(reproduce, "session_for", lambda run_id: _Session(result))
    return reproduce.reproduce_once({"run_id": "r1", **state})


# --- reading the CI log ---

def test_failing_tests_read_from_a_github_actions_log():
    log = (FIXTURES / "F-02b" / "raw.log").read_text(encoding="utf-8")
    assert failing_tests(log) == ["tests/test_calc.py::test_running_total"]


def test_collection_error_is_kept_as_the_file_and_banners_are_ignored():
    log = (FIXTURES / "F-01" / "raw.log").read_text(encoding="utf-8")
    assert failing_tests(log) == ["tests/test_api.py"]


def test_ansi_codes_and_repeats_are_dropped():
    log = "\x1b[31mFAILED tests/a.py::t1\x1b[0m - x\nFAILED tests/a.py::t1 - x\nERROR tests/b.py::t2\n"
    assert failing_tests(log) == ["tests/a.py::t1", "tests/b.py::t2"]


def test_isolate_error_records_the_ci_failing_tests():
    log = (FIXTURES / "F-02" / "raw.log").read_text(encoding="utf-8")
    assert isolate_error({"raw_log": log})["ci_failing_tests"] == ["tests/test_calc.py::test_add"]


# --- judging the reproduction ---

def test_a_different_failure_is_not_a_reproduction(monkeypatch):
    out = _reproduce(monkeypatch, _red("tests/b.py::other"), ci_failing_tests=["tests/a.py::target"])
    assert out["reproduced"] is False
    assert "tests/a.py::target" in out["analysis_error"] and "tests/b.py::other" in out["analysis_error"]


def test_the_ci_failure_among_others_is_a_reproduction(monkeypatch):
    out = _reproduce(monkeypatch, _red("tests/a.py::target", "tests/b.py::other"),
                     ci_failing_tests=["tests/a.py::target"])
    assert out["reproduced"] is True
    assert out["target_tests"] == ["tests/a.py::target"] and out["repro_evidence"] == "ci_log"


def test_a_different_rootdir_prefix_still_matches(monkeypatch):
    out = _reproduce(monkeypatch, _red("pkg/tests/a.py::target"), ci_failing_tests=["tests/a.py::target"])
    assert out["reproduced"] is True


def test_without_ids_in_the_log_the_diagnosis_names_the_test(monkeypatch):
    analysis = Analysis(category="assertion_error", confidence=0.9, evidence="e",
                        proposed_action="p", failing_test="tests/a.py::target")
    out = _reproduce(monkeypatch, _red("tests/b.py::other"), ci_failing_tests=[], analysis=analysis)
    assert out["reproduced"] is False and out["repro_evidence"] == "diagnosis"


def test_with_no_test_ids_anywhere_a_red_run_is_flagged_as_weak_evidence(monkeypatch):
    out = _reproduce(monkeypatch, _red("tests/b.py::other"), ci_failing_tests=[])
    assert out["reproduced"] is True and out["repro_evidence"] == "exit_code"


def test_green_in_the_sandbox_says_why(monkeypatch):
    green = SandboxResult(step="test", exit_code=0, stdout_tail="3 passed", stderr_tail="",
                          duration_s=0.1, timed_out=False)
    out = _reproduce(monkeypatch, green, ci_failing_tests=["tests/a.py::target"])
    assert out["reproduced"] is False and "pass in the sandbox" in out["analysis_error"]


def test_every_key_reproduction_writes_is_declared():
    # LangGraph drops undeclared keys without a word (the pr_branch bug).
    out = {"ci_failing_tests": [], "target_tests": [], "repro_evidence": "", "reproduced": True}
    assert set(out) <= set(DebugState.__annotations__)
