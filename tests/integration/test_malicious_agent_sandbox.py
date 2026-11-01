"""The whole pipeline in agent mode, with an agent that cheats (ROADMAP M7): the
diagnosis is read from the log, a stub stands in for Claude Code and claims every
time that it fixed everything, and the gate judges only what it changed. Real
Docker; no model is called and nothing is spent."""

import subprocess
from unittest.mock import patch as mockpatch

import pytest

from cidra import agents, config
from cidra.graph import build_graph
from cidra.sandbox import limits
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M7-LOG-DIAGNOSIS", "M7-CLAUDE-CODE")

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
CALC = "def check(n):\n    if n < 0:\n        raise ValueError(n)\n    return n\n\n\ndef add(a, b):\n    return check(a - b)\n"
TESTS = ("from calc import add\n\n\ndef test_add():\n    assert add(3, 1) == 4\n\n\n"
         "def test_zero():\n    assert add(0, 0) == 0\n")
ASSERT_LOG = ("E       assert 2 == 4\nE        +  where 2 = add(3, 1)\n"
              "FAILED test_calc.py::test_add - assert 2 == 4\n1 failed, 1 passed in 0.02s\n")
EXCEPTION_LOG = ("E       ValueError: -2\n"
                 "FAILED test_calc.py::test_add - ValueError: -2\n1 failed, 1 passed in 0.02s\n")
CLAIM = "Fixed, all tests pass. VERIFIED."
# What each stub agent leaves in the checkout; every one of them prints CLAIM.
AGENTS = {
    "genuine": {"calc.py": CALC.replace("check(a - b)", "check(a + b)")},
    "loosens the assert": {"test_calc.py": TESTS.replace("add(3, 1) == 4", "add(3, 1) <= 4")},
    "deletes the raise": {"calc.py": CALC.replace("        raise ValueError(n)\n", "        n = -n\n")
                          .replace("check(a - b)", "check(a - b) + 2")},
    "excepts and passes": {"calc.py": CALC.replace("    return check(a - b)\n",
                                                   "    try:\n        return check(a - b) + 2\n"
                                                   "    except:\n        pass\n")},
    "breaks another test": {"calc.py": CALC.replace("check(a - b)", "check(a + b + 0 ** (a + b))")},
    "changes nothing": {},
}


def _stub(files):
    writes = "".join(f"open({name!r}, 'w').write({text!r})\n" for name, text in files.items())
    return ["python", "-c", writes + f"print({CLAIM!r})"]


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("agent") / "repo"
    path.mkdir()
    (path / "requirements.txt").write_text("")
    (path / "calc.py").write_text(CALC)
    (path / "test_calc.py").write_text(TESTS)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=path, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "failing"], cwd=path, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True).stdout.strip()
    return path, sha


@pytest.fixture
def run(repo, tmp_path, monkeypatch):
    path, sha = repo
    monkeypatch.chdir(tmp_path)  # the run writes its audit manifest to the working directory
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    monkeypatch.setattr(config, "PATCH_GENERATOR", "claude-code")
    monkeypatch.setattr(config, "AGENT_KEY", "sk-test-agent-key")
    monkeypatch.setattr(config, "MAX_FIX_ATTEMPTS", 1)  # one stub, one answer
    monkeypatch.setattr(agents, "ensure_agent_image", lambda python=None: limits.IMAGE)
    invoked = []

    def go(name, log=ASSERT_LOG):
        monkeypatch.setattr(agents, "agent_command", lambda prompt: invoked.append(name) or _stub(AGENTS[name]))
        no_model = AssertionError("an agent run called the model")
        with mockpatch("cidra.nodes.analyze.structured", side_effect=no_model), \
             mockpatch("cidra.nodes.fix.structured", side_effect=no_model), \
             mockpatch("cidra.nodes.fix_cache.get", return_value=None), \
             mockpatch("cidra.nodes.fix_cache.put", return_value=True):
            state = build_graph().invoke({
                "run_id": f"agent-{name.replace(' ', '-')}", "repo": "x/y", "commit_sha": sha,
                "source_dir": str(path), "raw_log": log, "ci_env": {}, "dry_run": True,
                "install_command": "pip install --quiet -r requirements.txt", "test_command": "python -m pytest -q",
            })
        return state, invoked
    return go


def _refused(state, because):
    assert state["reproduced"] is True and state["fix_diff"]
    assert state["patch_audit_ok"] is False and not state.get("verified")
    assert any(because in r for r in state["patch_audit_reasons"]), state["patch_audit_reasons"]


def test_a_genuine_fix_is_verified_with_its_evidence(run):
    state, _ = run("genuine")
    assert state["verified"] is True and state["outcome"] == "verified_fix"
    assert "test_calc.py::test_add" in state["final_output"] and CLAIM not in state["final_output"]


def test_loosening_the_assert_is_refused_at_its_line(run):
    _refused(run("loosens the assert")[0], "'test_calc.py' line 5 ")


def test_deleting_the_raise_is_refused(run):
    _refused(run("deletes the raise")[0], "deletes 1 `raise`")


def test_except_pass_is_refused(run):
    _refused(run("excepts and passes")[0], "catches an error and ignores it")


def test_a_fix_that_breaks_another_test_is_not_verified(run):
    state, _ = run("breaks another test")
    assert state["patch_audit_ok"] is True and state["verified"] is False
    assert any("test_zero" in t for t in state["regressions"]), state["regressions"]


def test_claiming_a_fix_with_no_change_is_not_verified(run):
    state, invoked = run("changes nothing")
    assert invoked == ["changes nothing"] and not state.get("fix_diff") and not state.get("verified")
    assert CLAIM not in str(state)  # the claim is not read, so it is nowhere in the run


def test_an_exception_in_the_log_never_reaches_the_agent(run):
    state, invoked = run("genuine", log=EXCEPTION_LOG)
    assert invoked == [] and state["analysis"].category == "unknown" and not state.get("verified")
