"""A key, endpoint or token saved through the settings API applies to the next
call of the running server, not only after a restart (KNOWN_GAPS G-19). Before,
the connection test saw a new key while every run kept the old one."""

import pytest

from cidra import config
from cidra.integrations import github, github_write, llm
from cidra.server import settings

pytestmark = pytest.mark.req("G-19")


@pytest.fixture
def scratch_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ENV_PATH", tmp_path / ".env")  # never the user's .env
    for attr in ("API_KEY", "BASE_URL", "GEMINI_API_KEY", "GITHUB_TOKEN", "GITHUB_TOKEN_RO", "WEBHOOK_SECRET"):
        monkeypatch.setattr(config, attr, getattr(config, attr))  # restored after the test
    for var in ("CIDRA_API_KEY", "CIDRA_BASE_URL", "GEMINI_API_KEY", "CIDRA_GITHUB_TOKEN",
                "CIDRA_GITHUB_TOKEN_RO", "CIDRA_WEBHOOK_SECRET"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / ".env"


def test_a_saved_model_key_and_endpoint_reach_the_next_call(scratch_env):
    config.API_KEY, config.BASE_URL = "old-key", "https://old.example/v1/"
    assert llm.client().api_key == "old-key"
    settings.save_settings({"keys": {"CIDRA_API_KEY": "new-key"}, "models": {"base_url": "https://new.example/v1/"}})
    used = llm.client()
    assert used.api_key == "new-key" and str(used.base_url) == "https://new.example/v1/"
    assert "CIDRA_API_KEY=new-key" in scratch_env.read_text(encoding="utf-8")


def test_saved_github_tokens_reach_the_next_call(scratch_env):
    config.GITHUB_TOKEN, config.GITHUB_TOKEN_RO = "old-write", ""
    settings.save_settings({"keys": {"CIDRA_GITHUB_TOKEN": "new-write"}})
    assert github_write._client().headers["Authorization"] == "Bearer new-write"
    # no read-only token: reads fall back to the write token saved just now, not the old one
    assert github._client().headers["Authorization"] == "Bearer new-write"
    settings.save_settings({"keys": {"CIDRA_GITHUB_TOKEN_RO": "new-read"}})
    assert github._client().headers["Authorization"] == "Bearer new-read"


def test_a_saved_webhook_secret_and_fallback_key_reach_the_server(scratch_env):
    settings.save_settings({"keys": {"CIDRA_WEBHOOK_SECRET": "s3cret", "GEMINI_API_KEY": "gem"}})
    assert config.WEBHOOK_SECRET == "s3cret"
    assert llm.gemini_client().api_key == "gem"


@pytest.fixture
def scratch_bounds(scratch_env, monkeypatch):
    for var in ("MAX_FIX_ATTEMPTS", "FLAKY_RUNS", "FLAKY_SCORE_THRESHOLD", "CONTAINER_TIMEOUT"):
        monkeypatch.setattr(config, var, getattr(config, var))
        monkeypatch.delenv(var, raising=False)


def test_saved_loop_and_timeout_settings_reach_the_next_run(scratch_bounds, monkeypatch):
    from types import SimpleNamespace

    from cidra.nodes import reproduce
    from cidra.routers import route_after_verify
    from cidra.sandbox import runner

    settings.save_settings({"flakiness": {"max_fix_attempts": 1, "flaky_runs": 7, "container_timeout": 120}})
    # one attempt allowed: a failed first fix goes to the report, not a second attempt
    assert route_after_verify({"verified": False, "fix_attempts": 1}) == "compose_report"
    runs = []
    session = SimpleNamespace(run=lambda step, cmd: runs.append(step) or SimpleNamespace(passed=True))
    monkeypatch.setattr(reproduce, "session_for", lambda run_id: session)
    reproduce.reproduce_n_times({"run_id": "r", "test_command": "pytest"})
    assert len(runs) == 7
    assert runner._timeout("test") == runner._timeout("verify") == 120
    assert runner._timeout("install") == 300  # the install step keeps its own limit
    shown = settings.get_current_settings()["flakiness"]
    assert (shown["max_fix_attempts"], shown["flaky_runs"], shown["container_timeout"]) == (1, 7, 120)


def test_a_saved_setting_out_of_bounds_is_clamped_not_obeyed(scratch_bounds):
    settings.save_settings({"flakiness": {"max_fix_attempts": 99, "flaky_runs": 1, "container_timeout": 1}})
    assert (config.MAX_FIX_ATTEMPTS, config.FLAKY_RUNS, config.CONTAINER_TIMEOUT) == (5, 2, 30)
    assert config.bounded("not a number", 3, 1, 5) == 3


def test_the_settings_are_read_from_the_environment_at_startup(monkeypatch):
    import importlib
    monkeypatch.setenv("MAX_FIX_ATTEMPTS", "2")
    monkeypatch.setenv("CONTAINER_TIMEOUT", "90")
    try:
        importlib.reload(config)
        assert (config.MAX_FIX_ATTEMPTS, config.CONTAINER_TIMEOUT) == (2, 90)
    finally:
        monkeypatch.delenv("MAX_FIX_ATTEMPTS")
        monkeypatch.delenv("CONTAINER_TIMEOUT")
        importlib.reload(config)
