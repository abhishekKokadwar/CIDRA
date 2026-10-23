"""The Claude Code patch generator (ROADMAP M7): what it asks, how it runs the
agent, and what it records. No Docker here; tests/integration runs it for real."""

import pytest

from cidra import agents, config
from cidra.integrations import llm
from cidra.nodes import fix

pytestmark = pytest.mark.req("M7-CLAUDE-CODE")


def test_it_is_registered_as_a_generator():
    assert fix.GENERATORS["claude-code"] is agents.claude_code_patch


def test_the_prompt_states_the_rules_the_gate_enforces_and_the_failure():
    text = agents.prompt_for({"target_tests": ["tests/test_calc.py::test_add"], "test_command": "pytest -q",
                              "failure_detail": "E   assert -1 == 3", "verify_note": "tests/test_x.py went red"})
    assert "not the tests" in text and "Do not silence the error" in text
    assert "tests/test_calc.py::test_add" in text and "assert -1 == 3" in text and "pytest -q" in text
    assert "previous attempt did not work: tests/test_x.py went red" in text


def test_the_agent_runs_headless_and_bare_with_its_own_spend_limit(monkeypatch):
    monkeypatch.setattr(config, "AGENT_MAX_USD", 0.5)
    monkeypatch.setattr(config, "AGENT_MODEL", "")
    cmd = agents.agent_command("fix it")
    assert cmd[:3] == ["claude", "-p", "fix it"] and "--bare" in cmd and "--model" not in cmd
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.5"
    monkeypatch.setattr(config, "AGENT_MODEL", "sonnet")
    assert agents.agent_command("x")[-2:] == ["--model", "sonnet"]


def test_no_key_is_an_error_before_any_container(monkeypatch):
    monkeypatch.setattr(config, "AGENT_KEY", "")
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setattr(agents, "ensure_agent_image", lambda *a: pytest.fail("no container without a key"))
    out = agents.claude_code_patch({"run_id": "r", "source_dir": "."})
    assert out["fix_diff"] is None and "CIDRA_AGENT_KEY" in out["analysis_error"]


def test_proxy_counted_usage_is_priced_with_cache_tokens(monkeypatch):
    llm.clear_latest_telemetry()
    llm.record_usage({"model": "claude-haiku-4-5", "input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 400, "cache_read_input_tokens": 1000})
    [call] = llm.get_latest_telemetry()
    assert call["tokens"] == {"prompt": 100 + 500 + 100, "completion": 50, "total": 750}
    assert call["user_prompt"] is None and call["system_prompt"] is None
    assert llm.cost_of([call])[0] == pytest.approx(700 / 1e6 * 1.0 + 50 / 1e6 * 5.0)
    llm.clear_latest_telemetry()
