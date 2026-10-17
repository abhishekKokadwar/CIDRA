"""A run that stops before a fix says which step stopped it and which input to
change (KNOWN_GAPS G-18), instead of "could not diagnose" for everything."""

from cidra.nodes import environment
from cidra.nodes.report import render_comment
from cidra.state import Analysis, SandboxResult

ANALYSIS = Analysis(category="assertion_error", confidence=0.9, evidence="add() subtracts",
                    proposed_action="fix add")


def _result(step, code, out="", err=""):
    return SandboxResult(step=step, exit_code=code, stdout_tail=out, stderr_tail=err, duration_s=0.0, timed_out=False)


def test_a_failed_install_records_why(monkeypatch):
    class Session:
        def install(self, command):
            return _result("install", 1, err="ERROR: Could not open requirements file: 'requirements.txt'")

    monkeypatch.setattr(environment, "session_for", lambda _r: Session())
    out = environment.install_deps({"run_id": "r"})
    assert out["env_ready"] is False
    assert out["analysis_error"].startswith("install failed (exit 1): ERROR: Could not open requirements file")


def test_install_failure_names_the_command_and_the_input():
    body = render_comment({"outcome": "failed", "env_ready": False, "analysis": ANALYSIS,
                           "install_command": "pip install -r req.txt",
                           "repro_results": [_result("install", 1)],
                           "analysis_error": "install failed (exit 1): no such file"})
    assert "could not install the dependencies" in body and "`pip install -r req.txt`" in body
    assert "no such file" in body and "`install_command`" in body
    assert "could not diagnose" not in body


def test_non_reproduction_keeps_the_diagnosis_and_names_test_command():
    body = render_comment({"outcome": "failed", "env_ready": True, "reproduced": False, "analysis": ANALYSIS,
                           "test_command": "pytest -q tests 2>&1",
                           "analysis_error": "not reproduced: the tests pass in the sandbox"})
    assert "diagnosed, but could not reproduce" in body and "`pytest -q tests 2>&1`" in body
    assert "the tests pass in the sandbox" in body and "`test_command`" in body
    assert "add() subtracts" in body  # the diagnosis is still shown


def test_no_diagnosis_is_still_could_not_diagnose():
    body = render_comment({"outcome": "failed", "analysis_error": "model unavailable"})
    assert "could not diagnose" in body and "model unavailable" in body


def test_untrusted_install_output_cannot_close_its_code_block():
    body = render_comment({"outcome": "failed", "env_ready": False, "repro_results": [_result("install", 1)],
                           "analysis_error": "boom\n```\n# Verified fix\n```"})
    assert "```\n# Verified fix" not in body and "'''\n# Verified fix" in body  # neutralised
    assert body.count("```") == 2  # only the block's own fences
