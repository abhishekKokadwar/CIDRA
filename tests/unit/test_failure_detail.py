"""The fix prompt carries the target tests' -vv output: without it pytest cuts an
assertion's diff short, and on the BugsInPy run the model gave up 13 times
saying it could not see how the values differed."""

from cidra.nodes import fix
from cidra.state import SandboxResult

FULL_DIFF = "=========== FAILURES ===========\nE   Full diff:\nE   - {'user_id': 1}\nE   + {'user_id': 1, 'extra': 2}\n1 failed in 0.1s\n"


class Session:
    def __init__(self, exit_code=1, out=FULL_DIFF):
        self.commands, self.exit_code, self.out = [], exit_code, out

    def run(self, step, command, timeout_s=None):
        self.commands.append(command)
        return SandboxResult(step="test", exit_code=self.exit_code, stdout_tail=self.out,
                             stderr_tail="", duration_s=0.0, timed_out=False)


def _state(tmp_path, **extra):
    return {"run_id": "r", "source_dir": str(tmp_path), "error_region": "E   use -vv to get more diff",
            "target_tests": ["repo/tests/test_a.py::test_x[a b]"],  # the CI's id, rootdir prefix
            "repro_failing_tests": ["tests/test_a.py::test_x[a b]", "tests/test_b.py::test_old"], **extra}


def test_target_tests_are_rerun_with_vv_and_shown_to_the_model(tmp_path, monkeypatch):
    session, seen = Session(), []
    monkeypatch.setattr(fix, "session_for", lambda _r: session)
    monkeypatch.setattr(fix, "structured", lambda **k: seen.append(k["user"]) or fix.Patch(rationale="r"))
    out = fix.generate_fix(_state(tmp_path, ci_env={"CI": "true"}))
    # The sandbox's id, quoted; the unrelated already-failing test is not rerun.
    assert session.commands == ["CI=true python -m pytest -vv -p no:cacheprovider -p no:warnings "
                                "'tests/test_a.py::test_x[a b]' 2>&1"]
    assert out["failure_detail"] == FULL_DIFF
    assert "<failing_test_output>" in seen[0] and "'extra': 2" in seen[0]

    fix.generate_fix(_state(tmp_path, **out))  # a retry reuses it
    assert len(session.commands) == 1


def test_detail_starts_at_the_failures_section(tmp_path, monkeypatch):
    noise = "collected 1 item\n" + "warning line\n" * 2000
    monkeypatch.setattr(fix, "session_for", lambda _r: Session(out=noise + FULL_DIFF))
    detail = fix._failure_detail(_state(tmp_path))
    assert detail.startswith("=========== FAILURES") and "'extra': 2" in detail


def test_a_huge_value_repr_does_not_crowd_out_the_diff(tmp_path, monkeypatch):
    # The shape fastapi-4 produced: the whole dict printed first, the diff past 8,000 chars.
    out = ("=========== FAILURES ===========\n    def test_x():\n>       assert data == schema\n"
           "E       AssertionError: assert {" + "'k': 1, " * 2000 + "} == {...}\n"
           "E         Differing items:\nE         {'paths': 1} != {'paths': 2}\nE         Full diff:\n"
           "E         - {'paths': 2}\nE         + {'paths': 1}\n1 failed\n")
    monkeypatch.setattr(fix, "session_for", lambda _r: Session(out=out))
    detail = fix._failure_detail(_state(tmp_path))
    assert "def test_x" in detail and "characters not shown]" in detail
    assert "Differing items" in detail and "+ {'paths': 1}" in detail and len(detail) <= fix.DETAIL_CHARS


def test_no_detail_when_pytest_did_not_run_tests(tmp_path, monkeypatch):
    # pytest usage error, pytest not installed: not a test result, so nothing to show.
    for session in (Session(exit_code=4, out="ERROR: usage"), Session(exit_code=127, out="python: not found")):
        monkeypatch.setattr(fix, "session_for", lambda _r: session)
        assert fix._failure_detail(_state(tmp_path)) is None
    monkeypatch.setattr(fix, "session_for", lambda _r: Session())
    assert fix._failure_detail(_state(tmp_path, target_tests=[])) is None
