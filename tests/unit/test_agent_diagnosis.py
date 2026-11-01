"""An agent run is diagnosed from the log, never by a model (ROADMAP M7): with a
patch generator other than the built-in loop, CIDRA holds no model credential,
so the diagnosis must cost nothing and still decline what is out of scope."""

import pytest

from cidra import config
from cidra.nodes import analyze as analyze_mod
from cidra.nodes.analyze import analyze, validate_analysis
from cidra.nodes.fix import STRATEGIES

pytestmark = pytest.mark.req("M7-LOG-DIAGNOSIS")

ASSERT_LOG = ("E       assert -1 == 3\nE        +  where -1 = add(1, 2)\n"
              "FAILED tests/test_calc.py::test_add - assert -1 == 3\n")
EXCEPTION_LOG = ("E       KeyError: 'dur'\n"
                 "FAILED tests/test_calc.py::test_add - KeyError: 'dur'\n")


@pytest.fixture
def agent_run(monkeypatch):
    def no_model(**kw):
        raise AssertionError("an agent run called the model")
    monkeypatch.setattr(analyze_mod, "structured", no_model)
    monkeypatch.setattr(config, "PATCH_GENERATOR", "claude-code")


def _state(log):
    return {"raw_log": log, "error_region": log, "ci_failing_tests": ["tests/test_calc.py::test_add"]}


def test_failed_asserts_go_to_the_agent_with_no_model_call(agent_run):
    out = analyze(_state(ASSERT_LOG))
    analysis = out["analysis"]
    assert analysis.category == "assertion_error" and "assertion_error" in STRATEGIES
    assert analysis.failing_test == "tests/test_calc.py::test_add" and "assert -1 == 3" in analysis.evidence
    assert "outcome" not in validate_analysis({**_state(ASSERT_LOG), **out})


@pytest.mark.parametrize("log", [EXCEPTION_LOG, "1 failed in 0.1s\n"])
def test_anything_but_failed_asserts_is_declined_with_no_model_call(agent_run, log):
    analysis = analyze(_state(log))["analysis"]
    # unknown has no repair strategy: the agent never runs
    assert analysis.category == "unknown" and "unknown" not in STRATEGIES


def test_the_built_in_loop_still_asks_the_model(monkeypatch):
    asked = []
    monkeypatch.setattr(analyze_mod, "analyze_region", lambda region: asked.append(region))
    monkeypatch.setattr(config, "PATCH_GENERATOR", "builtin")
    analyze(_state(ASSERT_LOG))
    assert asked == [ASSERT_LOG]
