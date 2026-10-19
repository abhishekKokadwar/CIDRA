"""The CI workflow's env reaches the tests even behind `cd sub && ...` (KNOWN_GAPS G-24).

Needs Docker and the sandbox image (CI builds both).
"""

import pytest

from cidra import config
from cidra.nodes.environment import close_session, install_deps, prepare_sandbox, sandbox_test_command, session_for
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)


@pytest.mark.req("G-24")
def test_a_test_command_that_changes_directory_still_sees_the_workflow_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INSTALL_COMMAND", None)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "test_env.py").write_text(
        "import os\n\n\ndef test_token():\n    assert os.environ.get('API_TOKEN') == 'tok value'\n")
    state = {"run_id": "it-g24", "source_dir": str(tmp_path), "ci_env": {"API_TOKEN": "tok value"},
             "test_command": "cd sub && python -m pytest -q 2>&1"}
    try:
        state.update(prepare_sandbox(state))
        state.update(install_deps(state))
        result = session_for("it-g24").run("test", sandbox_test_command(state))
    finally:
        close_session("it-g24")
    assert result.passed, result.stdout_tail[-600:]
