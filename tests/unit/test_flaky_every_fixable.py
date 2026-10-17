"""A failure CIDRA would patch is reproduced twice; one that flips is flaky, not fixable (KNOWN_GAPS G-16)."""

import pytest

from cidra.nodes import reproduce
from cidra.nodes.report import render_comment
from cidra.state import Analysis, SandboxResult

pytestmark = pytest.mark.req('R3')


def _run(failed=(), step="test"):
    summary = "".join(f"FAILED {t} - AssertionError\n" for t in failed)
    return SandboxResult(step=step, exit_code=1 if failed else 0, stdout_tail=summary,
                         stderr_tail="", duration_s=0.1, timed_out=False)


class _Session:


    def read_file(self, path, max_bytes=0):  # no JUnit report


        return None

    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    def run(self, step, command, timeout_s=None):
        self.calls += 1
        return self.results.pop(0)


def _analysis(category):
    return Analysis(category=category, confidence=0.9, evidence="e", proposed_action="p")


def _reproduce(monkeypatch, session, category="assertion_error"):
    monkeypatch.setattr(reproduce, "session_for", lambda run_id: session)
    return reproduce.reproduce_once({"run_id": "r1", "analysis": _analysis(category),
                                     "ci_failing_tests": ["tests/a.py::t"]})


def test_red_then_green_is_flaky_and_never_patched(monkeypatch):
    out = _reproduce(monkeypatch, _Session(_run(["tests/a.py::t"]), _run()))
    assert out["outcome"] == "flaky_detected" and out["reproduced"] is False
    assert out["flaky_pass_count"] == 1


def test_a_target_that_stops_failing_is_flaky(monkeypatch):
    session = _Session(_run(["tests/a.py::t"]), _run(["tests/b.py::other"]))
    out = _reproduce(monkeypatch, session)
    assert out["outcome"] == "flaky_detected"


def test_red_twice_is_a_reproduction(monkeypatch):
    session = _Session(_run(["tests/a.py::t"]), _run(["tests/a.py::t"]))
    out = _reproduce(monkeypatch, session)
    assert out["reproduced"] is True and "outcome" not in out
    assert session.calls == 2


def test_a_category_cidra_will_not_patch_runs_once(monkeypatch):
    session = _Session(_run(["tests/a.py::t"]))
    out = _reproduce(monkeypatch, session, category="unknown")
    assert out["reproduced"] is True and session.calls == 1


def test_flaky_report_counts_test_runs_not_the_install():
    state = {"outcome": "flaky_detected", "flaky_pass_count": 1, "flaky_score": 100,
             "repro_results": [_run(step="install"), _run(["tests/a.py::t"]), _run()]}
    assert "(1/2 runs passed)" in render_comment(state)
