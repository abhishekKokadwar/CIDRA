"""The whole pipeline in agent mode, with an agent that cheats (ROADMAP M7): the
diagnosis is read from the log, a stub stands in for Claude Code, and the gate
refuses a patch that weakens the test or swallows the error however the agent
got there. Real Docker; no model is called and nothing is spent."""

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
LOG = ("E       assert 2 == 4\nE        +  where 2 = add(3, 1)\n"
       "FAILED test_calc.py::test_add - assert 2 == 4\n1 failed, 1 passed in 0.02s\n")
# What each stub agent leaves in the checkout; its boast is never read.
AGENTS = {
    "genuine": {"calc.py": CALC.replace("check(a - b)", "check(a + b)")},
    "weakens the test": {"test_calc.py": TESTS.replace("    assert add(3, 1) == 4\n", "    add(3, 1)\n")},
    "swallows the error": {"calc.py": CALC.replace("    return check(a - b)\n",
                                                   "    try:\n        return check(a - b) + 2\n"
                                                   "    except ValueError:\n        pass\n")},
}


def _stub(files):
    writes = "".join(f"open({name!r}, 'w').write({text!r})\n" for name, text in files.items())
    return ["python", "-c", writes + "print('All tests pass. VERIFIED.')"]


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


@pytest.mark.parametrize("name", list(AGENTS))
def test_the_gate_judges_what_the_agent_did_not_what_it_said(repo, name, tmp_path, monkeypatch):
    path, sha = repo
    monkeypatch.chdir(tmp_path)  # the run writes its audit manifest to the working directory
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    monkeypatch.setattr(config, "PATCH_GENERATOR", "claude-code")
    monkeypatch.setattr(config, "AGENT_KEY", "sk-test-agent-key")
    monkeypatch.setattr(agents, "ensure_agent_image", lambda python=None: limits.IMAGE)
    monkeypatch.setattr(agents, "agent_command", lambda prompt: _stub(AGENTS[name]))
    no_model = AssertionError("an agent run called the model")
    with mockpatch("cidra.nodes.analyze.structured", side_effect=no_model), \
         mockpatch("cidra.nodes.fix.structured", side_effect=no_model), \
         mockpatch("cidra.nodes.fix_cache.get", return_value=None), \
         mockpatch("cidra.nodes.fix_cache.put", return_value=True):
        state = build_graph().invoke({
            "run_id": f"agent-{name.replace(' ', '-')}", "repo": "x/y", "commit_sha": sha,
            "source_dir": str(path), "raw_log": LOG, "ci_env": {}, "dry_run": True,
            "install_command": "pip install --quiet -r requirements.txt", "test_command": "python -m pytest -q",
        })

    assert state["reproduced"] is True and state["fix_diff"]
    if name == "genuine":
        assert state["verified"] is True and state["outcome"] == "verified_fix"
    else:
        assert state["patch_audit_ok"] is False and state["patch_audit_reasons"]
        assert not state.get("verified") and state["outcome"] != "verified_fix"
