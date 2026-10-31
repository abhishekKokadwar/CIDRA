"""Fix pull requests through the real gate (ROADMAP M8): a failing base commit and
one pull request per kind of fix, each checked by `cidra check-pr` in the sandbox.
No model, no key. Needs Docker and the sandbox image (CI builds both)."""

import argparse
import subprocess

import pytest

from cidra import cli, config
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M8-CHECK-PR")

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
CALC = "def check(n):\n    if n < 0:\n        raise ValueError(n)\n    return n\n\n\ndef add(a, b):\n    return check(a - b)\n"
TESTS = ("from calc import add\n\n\ndef test_add():\n    assert add(3, 1) == 4\n\n\n"
         "def test_zero():\n    assert add(0, 0) == 0\n")
PULL_REQUESTS = {
    "genuine": {"calc.py": CALC.replace("check(a - b)", "check(a + b)")},
    "weakens the test": {"test_calc.py": TESTS.replace("    assert add(3, 1) == 4\n", "    add(3, 1)\n")},
    "swallows the error": {"calc.py": CALC.replace("    return check(a - b)\n",
                                                   "    try:\n        return check(a - b) + 2\n"
                                                   "    except ValueError:\n        pass\n")},
    "breaks another test": {"calc.py": CALC.replace("check(a - b)", "check(a + b + 0 ** (a + b))")},
}
EXPECTED = {"genuine": ("verified", 0), "weakens the test": ("refused", 1),
            "swallows the error": ("refused", 1), "breaks another test": ("not_verified", 1)}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("pr") / "repo"
    path.mkdir()
    (path / "requirements.txt").write_text("")
    (path / "calc.py").write_text(CALC)
    (path / "test_calc.py").write_text(TESTS)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=path, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "failing"], cwd=path, check=True)
    for name, files in PULL_REQUESTS.items():
        branch = name.replace(" ", "-")
        subprocess.run(["git", "checkout", "-q", "-b", branch, "main"], cwd=path, check=True)
        for file, text in files.items():
            (path / file).write_text(text)
        subprocess.run([*GIT, "commit", "-q", "-am", name], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=path, check=True)
    return path


@pytest.mark.parametrize("name", list(PULL_REQUESTS))
def test_each_pull_request_gets_the_right_verdict(repo, name, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output.txt"))
    monkeypatch.setenv("CIDRA_INSTALL_COMMAND", "pip install --quiet -r requirements.txt")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = cli.check_pr_run(argparse.Namespace(base="main", head=name.replace(" ", "-"), source=str(repo),
                                               target=None, out=str(tmp_path / "verdict.md")))
    outcome, exit_code = EXPECTED[name]
    verdict = (tmp_path / "verdict.md").read_text(encoding="utf-8")
    assert ((tmp_path / "output.txt").read_text(), code) == (f"verdict={outcome}\n", exit_code), verdict
    if outcome == "verified":
        assert "| `test_calc::test_add` (target) | failed | passed |" in verdict
    if name == "breaks another test":
        assert "test_zero" in verdict  # the regression is named
