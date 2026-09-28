"""Tests for CIDRA Dashboard API endpoints.

Verifies that the backend correctly wires up with the React dashboard:
- GET /api/settings: returns masked credentials, models, and sandbox thresholds
- POST /api/settings: persists updates to .env and updates in-memory config
- POST /api/settings/test: probes AI provider endpoints and returns latency
- GET /api/runs: returns recent execution telemetry runs
- POST /api/runs/{run_id}/approve: processes HITL gate approval
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from cidra import config
from cidra.server import app as appmod
from cidra.server import settings as settingsmod


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Fixture providing a TestClient with a sandbox .env file."""
    # Ensure webhook secret is set so app lifespan does not fail
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "test_secret_123")
    
    # Create isolated .env file
    test_env = tmp_path / ".env"
    test_env.write_text(
        "CIDRA_API_KEY=sk-or-v1-testkey1234567890abcdef\n"
        "CIDRA_BASE_URL=https://openrouter.ai/api/v1\n"
        "CIDRA_MODEL_ANALYZE=anthropic/claude-haiku-4.5\n"
        "CIDRA_MODEL_FIX=anthropic/claude-sonnet-4.5\n"
        "NVIDIA_API_KEY_KIMI=nvapi-testkimi1234567890\n"
        "GROQ_API_KEY=gsk_testgroq1234567890\n"
        "CIDRA_GITHUB_TOKEN=github_pat_test1234567890\n"
        "CIDRA_WEBHOOK_SECRET=test_secret_123\n"
        "FLAKY_RUNS=5\n"
        "FLAKY_SCORE_THRESHOLD=1\n"
        "MAX_FIX_ATTEMPTS=3\n"
        "CIDRA_ENABLE_PR_CREATION=false\n",
        encoding="utf-8"
    )
    monkeypatch.setattr(settingsmod, "ENV_PATH", test_env)
    
    return TestClient(appmod.app)


def test_get_settings_structure(client):
    """Verify GET /api/settings returns all required keys, models, and thresholds."""
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()

    # 1. Keys list
    assert "keys" in data
    assert isinstance(data["keys"], list)
    key_ids = [k["id"] for k in data["keys"]]
    assert "cidra_api_key" in key_ids
    assert "nvidia_kimi" in key_ids
    assert "groq_api_key" in key_ids
    assert "github_token" in key_ids
    assert "webhook_secret" in key_ids

    # Verify masking - secrets must never leak in cleartext
    for k in data["keys"]:
        if k["configured"]:
            assert "••••" in k["masked"], f"Secret for {k['id']} was not properly masked!"
            assert not k["masked"].startswith("sk-or-v1-testkey1234567890abcdef")

    # 2. Models
    assert "models" in data
    assert data["models"]["model_analyze"] == "anthropic/claude-haiku-4.5"
    assert data["models"]["model_fix"] == "anthropic/claude-sonnet-4.5"

    # 3. Flakiness & Sandbox
    assert "flakiness" in data
    assert data["flakiness"]["flaky_runs"] == 5
    assert data["flakiness"]["flaky_score_threshold"] == 1
    assert data["flakiness"]["max_fix_attempts"] == 3
    assert data["flakiness"]["enable_pr_creation"] is False

    # 4. System diagnostics
    assert "system" in data
    assert data["system"]["status"] == "operational"
    assert "python_version" in data["system"]


def test_post_settings_persists_to_env_and_config(client):
    """Verify POST /api/settings updates the .env file and updates in-memory config."""
    payload = {
        "models": {
          "model_analyze": "nvidia/nemotron-3-super-120b-a12b:free",
          "model_fix": "anthropic/claude-3.5-sonnet"
        },
        "flakiness": {
          "flaky_runs": 10,
          "flaky_score_threshold": 20,
          "max_fix_attempts": 2,
          "container_timeout": 120,
          "enable_pr_creation": True,
          "practice_repo": "custom/test-repo"
        }
    }

    res = client.post("/api/settings", json=payload)
    assert res.status_code == 200
    data = res.json()

    # Verify updated values in response
    assert data["models"]["model_analyze"] == "nvidia/nemotron-3-super-120b-a12b:free"
    assert data["models"]["model_fix"] == "anthropic/claude-3.5-sonnet"
    assert data["flakiness"]["flaky_runs"] == 10
    assert data["flakiness"]["flaky_score_threshold"] == 20
    assert data["flakiness"]["max_fix_attempts"] == 2
    assert data["flakiness"]["container_timeout"] == 120
    assert data["flakiness"]["enable_pr_creation"] is True
    assert data["flakiness"]["practice_repo"] == "custom/test-repo"

    # Verify in-memory config was updated
    assert config.MODEL_ANALYZE == "nvidia/nemotron-3-super-120b-a12b:free"
    assert config.MODEL_FIX == "anthropic/claude-3.5-sonnet"
    assert config.FLAKY_RUNS == 10
    assert config.FLAKY_SCORE_THRESHOLD == 20
    assert config.MAX_FIX_ATTEMPTS == 2
    assert config.ENABLE_PR_CREATION is True

    # Verify file on disk actually contains the updates
    saved_env = settingsmod.ENV_PATH.read_text(encoding="utf-8")
    assert "CIDRA_MODEL_ANALYZE=nvidia/nemotron-3-super-120b-a12b:free" in saved_env
    assert "CIDRA_MODEL_FIX=anthropic/claude-3.5-sonnet" in saved_env
    assert "FLAKY_RUNS=10" in saved_env
    assert "FLAKY_SCORE_THRESHOLD=20" in saved_env
    assert "MAX_FIX_ATTEMPTS=2" in saved_env
    assert "CIDRA_ENABLE_PR_CREATION=true" in saved_env
    assert "CIDRA_PRACTICE_REPO_SLUG=custom/test-repo" in saved_env


def test_post_settings_updates_api_keys_securely(client):
    """Verify new unmasked keys update .env, but masked keys are ignored."""
    # 1. Update with a new real key
    payload = {
        "keys": {
            "CIDRA_API_KEY": "sk-or-v1-newsecret9876543210zyxw"
        }
    }
    res = client.post("/api/settings", json=payload)
    assert res.status_code == 200

    saved_env = settingsmod.ENV_PATH.read_text(encoding="utf-8")
    assert "CIDRA_API_KEY=sk-or-v1-newsecret9876543210zyxw" in saved_env
    assert config.API_KEY == "sk-or-v1-newsecret9876543210zyxw"

    # 2. Sending masked secret does NOT overwrite with dots
    masked_payload = {
        "keys": {
            "CIDRA_API_KEY": "sk-or-v••••••••zyxw"
        }
    }
    client.post("/api/settings", json=masked_payload)
    saved_env_after = settingsmod.ENV_PATH.read_text(encoding="utf-8")
    assert "••••" not in saved_env_after
    assert "CIDRA_API_KEY=sk-or-v1-newsecret9876543210zyxw" in saved_env_after


def test_provider_connection_test(client):
    """Verify POST /api/settings/test returns latency and status."""
    # Mock urllib response for OpenRouter ping
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.post("/api/settings/test", json={"provider_id": "cidra_api_key"})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "latency_ms" in data
        assert data["message"] == "OpenRouter verified"


def test_list_runs_endpoint(client, monkeypatch):
    """Verify GET /api/runs returns run history for Command Center."""
    mock_runs = [
        {"id": "t-001", "status": "success", "fix": "Added missing import", "time": "12:00"},
        {"id": "t-002", "status": "error", "fix": "Assertion failed", "time": "12:05"}
    ]
    monkeypatch.setattr("cidra.history.load", lambda limit=50: mock_runs)

    res = client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()
    assert len(runs) == 2
    assert runs[0]["id"] == "t-001"
    assert runs[1]["id"] == "t-002"


def test_approve_run_hitl_gate(client, monkeypatch):
    """Verify POST /api/runs/{run_id}/approve processes approval."""
    mock_state = {"run_id": "run-xyz", "status": "verified_fix"}
    monkeypatch.setattr("cidra.history.load_full_state", lambda run_id: mock_state if run_id == "run-xyz" else None)

    # Valid run
    res = client.post("/api/runs/run-xyz/approve")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    # Nonexistent run -> 404
    res_404 = client.post("/api/runs/nonexistent/approve")
    assert res_404.status_code == 404
