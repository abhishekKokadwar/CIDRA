"""The install ladder in the real sandbox (ROADMAP M4): a pyproject-only package
gets its dependencies with no install command configured, and a repository with
nothing to install still runs. Needs Docker, the sandbox image and PyPI access
for the install step (CI has all three)."""

import pytest

from cidra import config
from cidra.nodes.environment import close_session, install_deps, prepare_sandbox, sandbox_test_command, session_for
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon, no image: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M4-INSTALL")


def _run(tmp_path, monkeypatch, run_id, files):
    monkeypatch.setattr(config, "INSTALL_COMMAND", None)
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    state = {"run_id": run_id, "source_dir": str(tmp_path), "test_command": "python -m pytest -q 2>&1"}
    try:
        state.update(prepare_sandbox(state))
        state.update(install_deps(state))
        tests = session_for(run_id).run("test", sandbox_test_command(state)) if state["env_ready"] else None
    finally:
        close_session(run_id)
    return state, tests


def test_a_pyproject_package_gets_its_dependencies_without_configuration(tmp_path, monkeypatch):
    state, tests = _run(tmp_path, monkeypatch, "it-ladder-pyproject", {
        "pyproject.toml": "[build-system]\nrequires=['setuptools>=61']\nbuild-backend='setuptools.build_meta'\n"
                          "[project]\nname='ladder_demo'\nversion='0.1'\ndependencies=['six']\n",
        "ladder_demo/__init__.py": "",
        "tests/test_dep.py": "import six\n\n\ndef test_dependency_installed():\n    assert six.PY3\n"})
    assert state["env_ready"], state.get("analysis_error")
    assert tests.passed, tests.stdout_tail[-500:]


def test_a_repo_with_nothing_to_install_still_runs(tmp_path, monkeypatch):
    state, tests = _run(tmp_path, monkeypatch, "it-ladder-none",
                        {"test_ok.py": "def test_ok():\n    assert True\n"})
    assert state["env_ready"], state.get("analysis_error")
    assert tests.passed
