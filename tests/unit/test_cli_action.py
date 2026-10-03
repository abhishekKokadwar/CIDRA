"""Action mode must target the commit whose CI failed, not GITHUB_SHA."""

import json

from cidra import cli


def _run(monkeypatch, tmp_path, event, **env):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", "111")
    monkeypatch.setenv("GITHUB_SHA", "main-tip-sha")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/ws")
    monkeypatch.delenv("CIDRA_SOURCE_DIR", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    seen = {}
    monkeypatch.setattr(cli, "_run_graph", seen.update)
    cli.action_run()
    return seen


def test_workflow_run_uses_head_sha_of_the_failed_run(monkeypatch, tmp_path):
    state = _run(monkeypatch, tmp_path, {"workflow_run": {
        "id": 999, "head_sha": "failing-sha", "head_branch": "feature",
        "pull_requests": [{"number": 7, "head": {"ref": "feature"}}],
    }})
    assert state["commit_sha"] == "failing-sha"
    assert state["run_id"] == "999"
    assert state["issue_number"] == 7 and state["pr_branch"] == "feature"
    assert state["base_branch"] == "feature"  # a new fix PR targets the failing branch


def test_other_events_fall_back_to_github_sha(monkeypatch, tmp_path):
    state = _run(monkeypatch, tmp_path, {})
    assert state["commit_sha"] == "main-tip-sha"
    assert state["source_dir"] == "/ws"


def test_source_dir_override(monkeypatch, tmp_path):
    state = _run(monkeypatch, tmp_path, {}, CIDRA_SOURCE_DIR="/ws/cidra-target")
    assert state["source_dir"] == "/ws/cidra-target"
