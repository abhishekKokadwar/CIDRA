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


# --- the Python version the sandbox should run ---

def _workflow(tmp_path, body):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ci.yml").write_text(body, encoding="utf-8")
    return tmp_path


def _setup_python(version_line, matrix=""):
    return ("jobs:\n  test:\n" + matrix + "    steps:\n      - uses: actions/setup-python@v5\n"
            "        with:\n          python-version: " + version_line + "\n")


def test_python_version_read_from_setup_python(tmp_path):
    from cidra.nodes.environment import workflow_python
    assert workflow_python(_workflow(tmp_path, _setup_python('"3.8"'))) == "3.8"
    assert workflow_python(_workflow(tmp_path, _setup_python("3.9.18"))) == "3.9"
    # unquoted 3.10 is the YAML float 3.1
    assert workflow_python(_workflow(tmp_path, _setup_python("3.10"))) == "3.10"


def test_python_version_matrix_takes_the_first_supported_entry(tmp_path):
    from cidra.nodes.environment import workflow_python
    matrix = '    strategy:\n      matrix:\n        python-version: ["pypy3.10", "3.9", "3.12"]\n'
    body = _setup_python("${{ matrix.python-version }}", matrix)
    assert workflow_python(_workflow(tmp_path, body)) == "3.9"


def test_python_version_falls_back_to_the_default(tmp_path):
    from cidra.nodes.environment import workflow_python
    from cidra.sandbox import limits
    assert workflow_python(tmp_path) == limits.DEFAULT_PYTHON
    assert workflow_python(_workflow(tmp_path, _setup_python('"3.x"'))) == limits.DEFAULT_PYTHON
    assert workflow_python(_workflow(tmp_path, _setup_python('"2.7"'))) == limits.DEFAULT_PYTHON
    (tmp_path / ".python-version").write_text("3.12.4\n")
    assert workflow_python(tmp_path) == "3.12"
    assert limits.image_for("3.12") == "cidra-sandbox:py3.12"
    assert limits.image_for("3.11") == limits.image_for(None) == limits.image_for("9.9") == limits.IMAGE


# --- the install and test commands the sandbox runs ---

def test_install_and_test_commands_default_and_per_run_override():
    from cidra import config
    from cidra.nodes.environment import sandbox_install_command, sandbox_test_command
    assert sandbox_install_command({}) == config.INSTALL_COMMAND
    assert sandbox_test_command({}) == config.TEST_COMMAND
    state = {"install_command": "pip install --quiet .", "test_command": "pytest -q tests/unit 2>&1",
             "ci_env": {"API_TOKEN": "tok value"}}
    assert sandbox_install_command(state) == "pip install --quiet ."
    assert sandbox_test_command(state) == "API_TOKEN='tok value' pytest -q tests/unit 2>&1"
