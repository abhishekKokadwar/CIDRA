"""CIDRA's scope is read from the log, not taken from the model: a failure whose
log shows an exception escaping the code under test is declined even when the
model calls it an assertion error (corpus v6: tornado-9 and youtube-dl-6 were
"verified" that way and judged wrong by their held-out tests)."""

import pathlib

import pytest

from cidra.nodes.analyze import validate_analysis
from cidra.nodes.fix import STRATEGIES
from cidra.nodes.ingest import failures_are_asserts
from cidra.state import Analysis

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.req("M3-SCOPE")

ASSERT_LOG = ("FAILED tests/test_calc.py::test_add - assert -1 == 3\n"
              "E       assert -1 == 3\nE        +  where -1 = add(1, 2)\n")
EXCEPTION_LOG = ("E       TypeError: 'args' parameter should be dict, list or tuple. Not <class 'NoneType'>\n"
                 "FAILED tornado/test/httputil_test.py::UrlConcatTest::test_url_concat_none_params\n")


def _analysis(category="assertion_error"):
    return Analysis(category=category, confidence=0.9, evidence="e", proposed_action="p",
                    failing_test="tests/test_calc.py::test_add")


def test_an_exception_called_an_assertion_by_the_model_is_declined():
    out = validate_analysis({"analysis": _analysis(), "raw_log": EXCEPTION_LOG})
    # unknown has no repair strategy: the run reproduces and reports, never patches
    assert out["analysis"].category == "unknown" and "unknown" not in STRATEGIES
    assert any("outside CIDRA's scope" in r and "TypeError" in r for r in out["policy_reasons"])


def test_a_failed_assert_stays_in_scope():
    assert "analysis" not in validate_analysis({"analysis": _analysis(), "raw_log": ASSERT_LOG})


def test_no_failure_detail_in_the_log_leaves_the_model_to_decide():
    assert "analysis" not in validate_analysis({"analysis": _analysis(), "raw_log": "1 failed in 0.1s\n"})


def test_github_timestamps_and_continuation_lines_are_read_correctly():
    log = ("2026-08-21T14:50:12.9946158Z E       AssertionError: Lists differ: [1, 1] != [1, 2]\n"
           "2026-08-21T14:50:12.9946158Z E       \n"
           "2026-08-21T14:50:12.9946158Z E       First differing element 1:\n")
    assert failures_are_asserts(log) is True
    assert failures_are_asserts("2026-08-21T14:50:12Z E   KeyError: 'dur'\n") is False


@pytest.mark.parametrize("fixture", ["bip-tornado-9", "bip-youtube-dl-6", "bip-youtube-dl-10"])
def test_the_v6_out_of_scope_cases_are_declined_from_their_logs(fixture):
    log = (ROOT / "eval" / "corpus" / fixture / "raw.log").read_text(encoding="utf-8")
    assert validate_analysis({"analysis": _analysis(), "raw_log": log})["analysis"].category == "unknown"


def test_failed_asserts_called_unknown_by_the_model_are_attempted():
    out = validate_analysis({"analysis": _analysis("unknown"), "raw_log": ASSERT_LOG})
    assert out["analysis"].category == "assertion_error" and "assertion_error" in STRATEGIES
    assert any("in CIDRA's scope" in r for r in out["policy_reasons"])


def test_unknown_stays_unknown_on_an_exception_or_no_detail():
    for log in (EXCEPTION_LOG, "1 failed in 0.1s\n"):
        assert "analysis" not in validate_analysis({"analysis": _analysis("unknown"), "raw_log": log})


@pytest.mark.parametrize("fixture", ["bip-thefuck-2", "bip-tornado-1", "bip-tornado-4", "bip-tornado-8", "bip-tornado-10"])
def test_the_v7_fixable_cases_declined_as_unknown_are_attempted(fixture):
    log = (ROOT / "eval" / "corpus" / fixture / "raw.log").read_text(encoding="utf-8")
    assert validate_analysis({"analysis": _analysis("unknown"), "raw_log": log})["analysis"].category == "assertion_error"
