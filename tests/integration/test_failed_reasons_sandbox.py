"""G-18 through the real sandbox and nodes: an install that fails and a failure
that does not reproduce each produce a report that says why and what to change.
Needs Docker and the sandbox image (CI builds both)."""

import pathlib

import pytest

from cidra.nodes.environment import close_session, install_deps, prepare_sandbox
from cidra.nodes.publish import compose_report
from cidra.nodes.report import render_comment
from cidra.nodes.reproduce import reproduce_once
from cidra.sandbox.runner import client
from cidra.state import Analysis

pytestmark = pytest.mark.req('M1-G18')

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon, no image: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

ANALYSIS = Analysis(category="assertion_error", confidence=0.9, evidence="add() subtracts",
                    proposed_action="fix add", failing_test="tests/test_calc.py::test_add")


def _repo(tmp_path: pathlib.Path, body: str) -> str:
    (tmp_path / "calc.py").write_text(f"def add(a, b):\n    return {body}\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    return str(tmp_path)


def _report(state: dict) -> str:
    return render_comment({**state, **compose_report(state)})


def test_a_failed_install_says_what_failed_and_which_input_to_set(tmp_path):
    state = {"run_id": "it-g18-install", "source_dir": _repo(tmp_path, "a - b"), "analysis": ANALYSIS,
             "install_command": "pip install --quiet -r no-such-requirements.txt"}
    try:
        prepare_sandbox(state)
        state.update(install_deps(state))
    finally:
        close_session("it-g18-install")
    assert state["env_ready"] is False
    body = _report(state)
    assert "could not install the dependencies" in body
    assert "no-such-requirements.txt" in body  # pip's own message, from the real install
    assert "`install_command`" in body


def test_a_failure_that_does_not_reproduce_says_so_and_names_test_command(tmp_path):
    state = {"run_id": "it-g18-repro", "source_dir": _repo(tmp_path, "a + b"), "analysis": ANALYSIS,  # already green
             "env_ready": True, "test_command": "python -m pytest -q 2>&1",
             "ci_failing_tests": ["tests/test_calc.py::test_add"]}
    try:
        prepare_sandbox(state)
        state.update(reproduce_once(state))
    finally:
        close_session("it-g18-repro")
    assert state["reproduced"] is False
    body = _report(state)
    assert "diagnosed, but could not reproduce" in body
    assert "the tests pass in the sandbox" in body and "`test_command`" in body
