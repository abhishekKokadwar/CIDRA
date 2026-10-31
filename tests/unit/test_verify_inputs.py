"""`cidra verify` takes the fix from wherever it was written (ROADMAP M8): a diff
file, stdin (`--patch -`), or a branch diffed against the failing commit
(`--branch`). No Docker: each case is told apart before the sandbox."""

import argparse
import io
import subprocess
import sys

import pytest

from cidra import cli, config
from cidra.nodes import environment

pytestmark = pytest.mark.req("M8-VERIFY-ANY-DIFF")

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A failing commit, and branches off it: a real fix, a cheat, and nothing."""
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    path = tmp_path / "repo"
    path.mkdir()
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (path / "test_calc.py").write_text(TEST)

    def git(*args):
        subprocess.run([*GIT, *args], cwd=path, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "failing")
    for branch, name, text in (("fix", "calc.py", "def add(a, b):\n    return a + b\n"),
                               ("cheat", "test_calc.py", TEST.replace("assert add(1, 2) == 3", "pass")),
                               ("nothing", None, None)):
        git("checkout", "-q", "-b", branch, "main")
        if name:
            (path / name).write_text(text)
            git("commit", "-q", "-am", branch)
    git("checkout", "-q", "main")
    return path


def _verify(repo, monkeypatch, reached, **source):
    monkeypatch.setattr(environment, "prepare_sandbox",
                        lambda state: reached.append(state) or {"env_ready": False, "analysis_error": "no sandbox here"})
    args = {"patch": None, "branch": None, **source}
    return cli.verify_run(argparse.Namespace(**args, sha="main", source=str(repo), install=None,
                                             test="python -m pytest -q", target=["test_calc.py::test_add"]))


def test_a_branch_is_diffed_against_the_failing_commit(repo):
    diff = cli._read_patch(argparse.Namespace(branch="fix", patch=None, sha="main", source=str(repo)))
    assert "-    return a - b\n+    return a + b\n" in diff and "test_calc.py" not in diff


def test_a_cheating_branch_is_refused_and_an_honest_one_goes_on(repo, monkeypatch, capsys):
    reached: list = []
    assert _verify(repo, monkeypatch, reached, branch="cheat") == 1
    assert "Refused by the audit gate" in capsys.readouterr().out and not reached
    _verify(repo, monkeypatch, reached, branch="fix")
    assert reached and "Refused" not in capsys.readouterr().out


def test_a_diff_on_stdin(repo, monkeypatch, capsys):
    cheat = cli._read_patch(argparse.Namespace(branch="cheat", patch=None, sha="main", source=str(repo)))
    monkeypatch.setattr(sys, "stdin", io.StringIO(cheat))
    assert _verify(repo, monkeypatch, [], patch="-") == 1
    assert "Refused by the audit gate" in capsys.readouterr().out


@pytest.mark.parametrize("branch, says", [("nothing", "The patch is empty"), ("no-such-branch", "Could not read the patch")])
def test_no_diff_is_an_error_not_a_pass(repo, monkeypatch, capsys, branch, says):
    reached: list = []
    assert _verify(repo, monkeypatch, reached, branch=branch) == 1
    assert says in capsys.readouterr().out and not reached


def test_a_patch_and_a_branch_together_are_refused():
    out = subprocess.run([sys.executable, "-m", "cidra.cli", "verify", "--patch", "x.diff", "--branch", "fix"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "not allowed with" in out.stderr
