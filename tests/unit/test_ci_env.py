"""The sandbox must see the env the repo's CI workflow sets, as data."""

from cidra.nodes.analyze import analyze
from cidra.nodes.environment import env_prefix, workflow_env

WORKFLOW = """
on: [push]
env:
  TOP: "1"
jobs:
  test:
    env:
      API_TOKEN: tok_practice_value
      SECRET: ${{ secrets.SECRET }}
      "bad name": x
    steps:
      - run: pytest
        env:
          STEP_FLAG: true
"""


def test_workflow_env_takes_literals_and_skips_expressions(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    assert workflow_env(tmp_path) == {
        "TOP": "1", "API_TOKEN": "tok_practice_value", "STEP_FLAG": "true"}
    assert workflow_env(tmp_path, ".github/workflows/ci.yml")["API_TOKEN"] == "tok_practice_value"


def test_workflow_env_without_workflows_is_empty(tmp_path):
    assert workflow_env(tmp_path) == {}


def test_env_prefix_quotes_values_and_drops_bad_names():
    prefix = env_prefix({"ci_env": {"A": "x; rm -rf /", "B": "ok", "bad;name": "y"}})
    assert prefix == "A='x; rm -rf /' B=ok "


def test_malformed_identifiers_are_refused_before_anything_runs():
    from cidra.nodes.ingest import fetch_log, invalid_identifier

    ok = {"repo": "o/r", "run_id": "local-1a2b", "commit_sha": "HEAD", "raw_log": "x"}
    assert invalid_identifier(ok) is None and fetch_log(ok) == {}
    for field, value in (("commit_sha", "--upload-pack=x"), ("repo", "o/r; rm -rf /"),
                         ("run_id", "../../etc")):
        out = fetch_log({**ok, field: value})
        assert out["raw_log"] == "" and field in out["analysis_error"]


def test_analyze_does_not_call_the_model_on_an_empty_log(monkeypatch):
    def boom(_region):
        raise AssertionError("model was called")
    monkeypatch.setattr("cidra.nodes.analyze.analyze_region", boom)
    out = analyze({"error_region": "", "analysis_error": "log fetch failed: 401"})
    assert out["analysis"] is None and out["analysis_error"] == "log fetch failed: 401"
    assert out["analysis_attempts"] >= 2  # no retry
