"""The evidence block a reviewer checks a fix from (ROADMAP M2)."""

import pytest

from cidra import evidence
from cidra.nodes.report import render_comment
from cidra.state import Analysis

pytestmark = pytest.mark.req("M2-EVIDENCE")

BEFORE = {"tests.test_calc::test_add": "failed", "tests.test_calc::test_zero": "passed",
          "tests.test_calc::test_div": "passed", "tests.test_io::test_old": "failed",
          "tests.test_calc::test_skip": "skipped"}
AFTER = {**BEFORE, "tests.test_calc::test_add": "passed", "tests.test_calc::test_div": "failed"}


def _state(**extra):
    return {"image_tag": "cidra-sandbox:base@sha256:abc", "commit_sha": "0123456789abcdef", "python_version": "3.11",
            "test_command": "pytest -q 2>&1", "install_command": "pip install -r requirements.txt",
            "target_tests": ["tests/test_calc.py::test_add"], "repro_junit": BEFORE, "verify_junit": AFTER, **extra}


def test_pytest_ids_map_to_junit_ids():
    assert evidence.junit_id("tests/test_a.py::test_y[p q]") == "tests.test_a::test_y[p q]"
    assert evidence.junit_id("tests/test_a.py::TestX::test_y") == "tests.test_a.TestX::test_y"


def test_the_table_shows_the_target_what_changed_and_what_was_already_failing():
    rows = evidence.test_rows(_state())
    assert "| `tests.test_calc::test_add` (target) | failed | passed |" in rows
    assert "| `tests.test_calc::test_div` **(now failing)** | passed | failed |" in rows
    assert "| `tests.test_io::test_old` | failed | failed |" in rows
    assert "| 2 other tests, unchanged | 1 passed, 1 skipped | same |" in rows


def test_repository_test_names_cannot_break_the_table():
    rows = evidence.test_rows(_state(target_tests=[], repro_junit={"t::x|`evil`\n| fake | row |": "failed"},
                                     verify_junit={}))
    assert rows[2:] == ["| `t::x evil fake row` | failed | not run |"]


def test_dependency_lines_the_patch_adds_are_surfaced():
    diff = ("--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1,2 @@\n pytest\n+requests==2.32.0\n"
            "--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1 @@\n-a\n+b\n")
    assert evidence.dependency_changes(diff) == ["requirements.txt: requests==2.32.0"]


def test_the_block_names_what_ran_and_the_audit_verdict():
    text = "\n".join(evidence.render(_state(patch_audit_ok=False, patch_audit_reasons=["SR-13: deletes a test"],
                                            fix_diff="--- a/x.py\n+++ b/x.py\n")))
    assert "`0123456789ab`" in text and "`cidra-sandbox:base@sha256:abc`" in text and "Python 3.11" in text
    assert "`pip install -r requirements.txt`" in text and "pytest -q 2>&1" in text
    assert "refused: SR-13: deletes a test" in text and "| Dependency change | none |" in text


def test_no_sandbox_no_block_and_every_report_carries_it_otherwise():
    assert evidence.render({"outcome": "failed"}) == []
    a = Analysis(category="assertion_error", confidence=0.9, evidence="e", proposed_action="p")
    body = render_comment({**_state(), "outcome": "verified_fix", "verified": True, "analysis": a,
                           "fix_diff": "--- a/calc.py\n+++ b/calc.py\n"})
    assert "<b>Evidence</b>" in body and "(target) | failed | passed" in body
