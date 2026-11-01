"""`cidra fix --agent claude-code` (ROADMAP M7): the named agent writes the patch,
and a missing credential stops the run before any sandbox work."""

import sys

import pytest

from cidra import cli, config
from cidra.nodes import fix

pytestmark = pytest.mark.req("M7-CLI-AGENT")


@pytest.fixture
def fix_run(monkeypatch):
    ran = []
    monkeypatch.setattr(cli, "_sandbox_log", lambda run_id, source, sha: ran.append("sandbox") or "log")
    monkeypatch.setattr(cli, "_run_graph", lambda state: ran.append(config.PATCH_GENERATOR) or state)
    monkeypatch.setattr(config, "PATCH_GENERATOR", "builtin")
    monkeypatch.delenv("CIDRA_PATCH_GENERATOR", raising=False)

    def go(*argv):
        monkeypatch.setattr(sys, "argv", ["cidra", "fix", *argv])
        cli.main()
        return ran
    return go


def test_the_agent_flag_picks_the_patch_generator(fix_run, monkeypatch):
    monkeypatch.setattr(config, "AGENT_KEY", "sk-ant-oat01-test")
    assert fix_run("--agent", "claude-code") == ["sandbox", "claude-code"]


def test_without_the_flag_the_built_in_loop_writes_the_patch(fix_run):
    assert fix_run() == ["sandbox", "builtin"]


def test_no_credential_stops_before_the_sandbox(fix_run, monkeypatch):
    monkeypatch.setattr(config, "AGENT_KEY", "")
    monkeypatch.setattr(config, "API_KEY", "")
    with pytest.raises(SystemExit) as stop:
        fix_run("--agent", "claude-code")
    assert "CIDRA_AGENT_KEY" in str(stop.value.code)


def test_an_unknown_agent_is_refused_and_every_choice_is_a_generator(fix_run, capsys):
    with pytest.raises(SystemExit):
        fix_run("--agent", "nope")
    assert "invalid choice" in capsys.readouterr().err
    assert "claude-code" in fix.GENERATORS
