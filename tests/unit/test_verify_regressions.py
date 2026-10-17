"""Verified = the CI's failing tests pass and nothing that passed before now fails (roadmap requirement 7)."""

import pytest

from cidra.nodes import fix
from cidra.nodes.report import render_comment
from cidra.state import DebugState, SandboxResult

pytestmark = pytest.mark.req('R7')

BEFORE = ["tests/a.py::target", "tests/old.py::already_broken"]


def _after(*failed, code=None):
    summary = "".join(f"FAILED {t} - AssertionError\n" for t in failed)
    exit_code = code if code is not None else (1 if failed else 0)
    return SandboxResult(step="verify", exit_code=exit_code, stdout_tail=summary,
                         stderr_tail="", duration_s=0.1, timed_out=False)


class _Session:


    def read_file(self, path, max_bytes=0):  # no JUnit report


        return None

    def __init__(self, result):
        self.result = result

    def run(self, step, command, timeout_s=None):
        return self.result


def _verify(monkeypatch, result, **state):
    monkeypatch.setattr(fix, "session_for", lambda run_id: _Session(result))
    base = {"run_id": "r1", "patch_applied": True, "fix_strategy": "patch_source",
            "target_tests": ["tests/a.py::target"], "repro_failing_tests": BEFORE}
    return fix.verify_fix({**base, **state})


def test_an_already_failing_unrelated_test_does_not_block_a_real_fix(monkeypatch):
    out = _verify(monkeypatch, _after("tests/old.py::already_broken"))
    assert out["verified"] is True
    assert out["verify_failing_tests"] == ["tests/old.py::already_broken"]


def test_a_test_that_passed_before_and_fails_now_is_a_regression(monkeypatch):
    out = _verify(monkeypatch, _after("tests/b.py::was_green"))
    assert out["verified"] is False
    assert out["regressions"] == ["tests/b.py::was_green"] and "broke" in out["verify_note"]


def test_the_target_still_failing_is_not_verified(monkeypatch):
    out = _verify(monkeypatch, _after("tests/a.py::target"))
    assert out["verified"] is False and "tests/a.py::target" in out["verify_note"]


def test_an_interrupted_run_proves_nothing(monkeypatch):
    out = _verify(monkeypatch, _after(code=2))
    assert out["verified"] is False and "exit 2" in out["verify_note"]


def test_without_a_known_target_only_a_green_run_verifies(monkeypatch):
    out = _verify(monkeypatch, _after("tests/old.py::already_broken"), target_tests=[])
    assert out["verified"] is False


def test_a_green_run_verifies(monkeypatch):
    assert _verify(monkeypatch, _after())["verified"] is True


def test_report_lists_tests_that_were_already_failing():
    body = render_comment({"outcome": "verified_fix", "fix_diff": "--- a/x\n+++ b/x\n",
                           "verify_failing_tests": ["tests/old.py::already_broken"]})
    assert "already failing before the patch" in body and "tests/old.py::already_broken" in body


def test_report_says_why_the_last_attempt_failed():
    body = render_comment({"outcome": "diagnosis_only",
                           "verify_note": "the patch broke tests that passed before: tests/b.py::was_green"})
    assert "tests/b.py::was_green" in body


def test_new_keys_are_declared():
    keys = {"repro_failing_tests", "verify_failing_tests", "regressions", "verify_note"}
    assert keys <= set(DebugState.__annotations__)
