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


def test_workflow_run_without_listed_prs_looks_the_pr_up(monkeypatch, tmp_path):
    # GitHub often sends pull_requests: [] even when the commit has an open PR.
    monkeypatch.setattr("cidra.integrations.github.open_pr_for_branch",
                        lambda repo, branch: 12 if (repo, branch) == ("o/r", "feature") else None)
    state = _run(monkeypatch, tmp_path, {"workflow_run": {
        "id": 999, "head_sha": "failing-sha", "head_branch": "feature", "pull_requests": []}})
    assert state["issue_number"] == 12 and state["pr_branch"] == "feature"


def test_pr_lookup_failure_means_no_pr(monkeypatch, tmp_path):
    def boom(repo, branch):
        raise RuntimeError("api down")
    monkeypatch.setattr("cidra.integrations.github.open_pr_for_branch", boom)
    state = _run(monkeypatch, tmp_path, {"workflow_run": {
        "id": 1, "head_sha": "s", "head_branch": "feature", "pull_requests": []}})
    assert state["issue_number"] is None and state["pr_branch"] is None


def test_every_initial_state_key_is_declared(monkeypatch, tmp_path):
    # LangGraph silently drops input keys the state schema does not declare, so an
    # undeclared key never reaches the node that needs it (pr_branch once did not).
    from cidra.state import DebugState

    state = _run(monkeypatch, tmp_path, {"workflow_run": {
        "id": 999, "head_sha": "failing-sha", "head_branch": "feature", "path": ".github/workflows/ci.yml",
        "pull_requests": [{"number": 7, "head": {"ref": "feature"}}],
    }})
    assert set(state) <= set(DebugState.__annotations__), set(state) - set(DebugState.__annotations__)
