"""`cidra verify` reruns a fix's verification in the real sandbox (ROADMAP M2):
the target must fail before the patch, pass after it, and nothing may break.
Needs Docker and the sandbox image (CI builds both)."""

import argparse
import subprocess

import pytest

from cidra import cli, config
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M2-RERUN")

GOOD = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
WRONG = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a * b\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    path = tmp_path / "repo"
    path.mkdir()
    (path / "requirements.txt").write_text("")
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (path / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
                                       "def test_zero():\n    assert add(0, 0) == 0\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    return path


def _verify(repo, patch: str) -> int:
    (repo.parent / "fix.diff").write_text(patch)
    return cli.verify_run(argparse.Namespace(
        patch=str(repo.parent / "fix.diff"), sha="HEAD", source=str(repo),
        install="pip install --quiet -r requirements.txt", test="python -m pytest -q 2>&1",
        target=["test_calc.py::test_add"]))


def test_a_real_fix_verifies_and_shows_the_target_going_green(repo, capsys):
    assert _verify(repo, GOOD) == 0
    out = capsys.readouterr().out
    assert "| `test_calc::test_add` (target) | failed | passed |" in out and "Verified." in out


def test_a_wrong_fix_does_not_verify(repo, capsys):
    # a * b: test_add (1*2 != 3) still fails, and test_zero still passes.
    assert _verify(repo, WRONG) == 1
    out = capsys.readouterr().out
    assert "Not verified" in out and "(target) | failed | failed |" in out


def test_a_patch_that_does_not_apply_says_so(repo, capsys):
    assert _verify(repo, GOOD.replace("a - b", "a / b")) == 1
    assert "does not apply" in capsys.readouterr().out
