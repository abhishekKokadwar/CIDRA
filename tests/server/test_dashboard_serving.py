"""What `cidra dashboard` serves a stranger: their own runs, every static file,
a start with nothing configured, and the .env of the project it runs in."""

import importlib

import pytest
from fastapi.testclient import TestClient

from cidra import config, history
from cidra.server import app as appmod


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # history and run_states live in the working directory
    monkeypatch.setattr(config, "RUN_HISTORY_PATH", str(tmp_path / "cidra_run_history.jsonl"))
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "")
    with TestClient(appmod.app, base_url="http://127.0.0.1") as c:  # runs the startup hook
        yield c


@pytest.mark.req("UI-OWN-RUNS")
def test_the_dashboard_shows_this_directorys_runs_not_the_bundled_sample(client):
    history.record({"run_id": "mine-1", "repo": "me/proj", "outcome": "diagnosis_only", "commit_sha": "abc"})
    data = client.get("/telemetry.json").json()
    assert [r["id"] for r in data["runs"]] == ["mine-1"]
    assert data["runs"][0]["repo"] == "me/proj" and data["stats"]["total_interventions"] == 1


@pytest.mark.req("UI-OWN-RUNS")
def test_with_no_runs_the_dashboard_is_empty(client):
    assert client.get("/telemetry.json").json()["runs"] == []


@pytest.mark.req("UI-STATIC")
def test_every_file_the_page_references_is_served(client):
    for path in ("/favicon.svg", "/cidra_logo.png", "/cidra_icon.png", "/icons.svg"):
        assert client.get(path).status_code == 200, path
    page = client.get("/", headers={"accept": "text/html"}).text
    for asset in [p.split('"')[0] for p in page.split('src="')[1:] + page.split('href="')[1:]]:
        if asset.startswith("/"):
            assert client.get(asset).status_code == 200, asset
    assert client.get("/nope.js").status_code == 404


@pytest.mark.req("UI-STARTS")
def test_the_server_starts_without_a_webhook_secret_and_refuses_deliveries(client):
    assert client.get("/").json()["ok"] is True
    r = client.post("/webhook", content=b"{}", headers={"X-GitHub-Event": "workflow_run"})
    assert r.status_code == 503 and "CIDRA_WEBHOOK_SECRET" in r.text


@pytest.mark.req("UI-ENV")
def test_settings_read_and_write_the_env_of_the_project_cidra_runs_in(monkeypatch, tmp_path):
    from cidra.server import settings
    env = tmp_path / "proj.env"
    env.write_text("CIDRA_MODEL_FIX=from-scratch-env\n", encoding="utf-8")
    monkeypatch.setenv("CIDRA_ENV_FILE", str(env))
    monkeypatch.delenv("CIDRA_MODEL_FIX", raising=False)
    try:
        importlib.reload(config)
        importlib.reload(settings)
        assert settings.ENV_PATH == env.resolve() and config.MODEL_FIX == "from-scratch-env"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
        importlib.reload(settings)


@pytest.mark.req("UI-TOKEN")
def test_with_a_dashboard_token_the_runs_need_it_too(client, monkeypatch):
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "t0k")
    assert client.get("/telemetry.json").status_code == 401
    assert client.get("/telemetry.json", headers={"X-CIDRA-Token": "t0k"}).status_code == 200


@pytest.mark.req("UI-OWN-RUNS")
def test_a_run_leaves_no_dashboard_folders_in_the_repository_it_ran_in(client, tmp_path):
    history.record({"run_id": "mine-2", "repo": "me/proj", "outcome": "verified_fix"})
    assert not (tmp_path / "dashboard").exists() and not (tmp_path / "cidra").exists()
    assert not (tmp_path / "cidra_telemetry.json").exists()
    assert [r["id"] for r in client.get("/telemetry.json").json()["runs"]] == ["mine-2"]


@pytest.mark.req("UI-EVIDENCE")
def test_each_run_carries_its_evidence_for_the_explorer(client):
    history.record({
        "run_id": "ev-1", "repo": "me/proj", "outcome": "verified_fix", "commit_sha": "abc123",
        "fix_diff": "--- a/x.py\n+++ b/x.py\n", "install_command": "pip install --quiet -r requirements.txt",
        "target_tests": ["tests/test_calc.py::test_add"],
        "repro_junit": {"tests.test_calc::test_add": "failed", "tests.test_calc::test_sub": "passed"},
        "verify_junit": {"tests.test_calc::test_add": "passed", "tests.test_calc::test_sub": "passed"},
        "llm_telemetry": [{"model": "claude-haiku-4-5", "tokens": {"prompt": 4000, "completion": 400, "total": 4400}}],
    })
    history.record({"run_id": "ev-2", "repo": "me/proj", "outcome": "verified_fix", "fix_diff": "x"})
    runs = {r["id"]: r["evidence"] for r in client.get("/telemetry.json").json()["runs"]}
    ev = runs["ev-1"]
    assert ev["tests"] == [{"test": "tests.test_calc::test_add", "before": "failed", "after": "passed", "note": "target"}]
    assert ev["unchanged"] == {"passed": 1}
    assert ev["cost_usd"] == 0.006 and ev["price_source"] == "list price"
    assert ev["rerun_command"].startswith("cidra verify --sha abc123 --patch fix.diff --install ")
    assert "'pip install --quiet -r requirements.txt'" in ev["rerun_command"]
    assert "--target tests/test_calc.py::test_add" in ev["rerun_command"]
    # No recorded install command (an older run): no rerun command, rather than a wrong one.
    assert runs["ev-2"]["rerun_command"] is None and runs["ev-2"]["tests"] == []
