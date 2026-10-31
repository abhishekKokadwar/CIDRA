"""`cidra verify` runs the audit gate before any sandbox work (ROADMAP M8): a diff
that weakens the failing test or silences an error is refused whatever wrote it,
and never run. No Docker: a refused diff must stop before the sandbox."""

import argparse
import subprocess

import pytest

from cidra import cli, config
from cidra.nodes import environment

pytestmark = pytest.mark.req("M8-VERIFY-AUDIT")

DELETE_ASSERT = ("--- a/test_calc.py\n+++ b/test_calc.py\n@@ -2,4 +2,4 @@\n \n \n def test_add():\n"
                 "-    assert add(1, 2) == 3\n+    pass\n")
SWALLOW = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,5 @@\n def add(a, b):\n-    return check(a - b)\n"
           "+    try:\n+        return check(a - b)\n+    except ValueError:\n+        pass\n")
GOOD = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return check(a - b)\n+    return check(a + b)\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    path = tmp_path / "repo"
    path.mkdir()
    (path / "calc.py").write_text("def add(a, b):\n    return check(a - b)\n")
    (path / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    return path


def _verify(repo, patch, monkeypatch, sandbox):
    monkeypatch.setattr(environment, "prepare_sandbox", sandbox)
    (repo.parent / "fix.diff").write_text(patch)
    return cli.verify_run(argparse.Namespace(patch=str(repo.parent / "fix.diff"), sha="HEAD", source=str(repo),
                                             install=None, test="python -m pytest -q",
                                             target=["test_calc.py::test_add"]))


def _never(state):
    pytest.fail("a refused diff must not reach the sandbox")


@pytest.mark.parametrize("patch, reason", [(DELETE_ASSERT, "test_calc.py"), (SWALLOW, "ignores it")])
def test_a_cheating_diff_is_refused_before_the_sandbox(repo, monkeypatch, capsys, patch, reason):
    assert _verify(repo, patch, monkeypatch, _never) == 1
    out = capsys.readouterr().out
    assert "Refused by the audit gate" in out and reason in out


def test_an_honest_diff_passes_the_gate_and_goes_on_to_the_sandbox(repo, monkeypatch, capsys):
    reached = []
    assert _verify(repo, GOOD, monkeypatch,
                   lambda state: reached.append(state) or {"env_ready": False, "analysis_error": "no sandbox here"}) == 1
    assert reached and "Refused" not in capsys.readouterr().out
