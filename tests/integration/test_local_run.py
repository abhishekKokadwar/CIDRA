"""`cidra fix` gets its failure log from the sandbox; the repo's code never runs on the host.

Needs Docker and the sandbox image (CI builds both).
"""

import argparse
import subprocess

import pytest

from cidra import cli, config
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)


def _repo(path, test_body: str):
    path.mkdir()
    (path / "requirements.txt").write_text("")
    # The test leaves a marker in its working directory: on the host, that is the repo.
    (path / "test_calc.py").write_text(
        "import pathlib\n\n\ndef test_add():\n"
        "    pathlib.Path('ran_here.txt').write_text('x')\n"
        f"    {test_body}\n"
    )
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    return path


def _run(monkeypatch, tmp_path, repo):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    seen = {}
    monkeypatch.setattr(cli, "_run_graph", seen.update)
    cli.local_run(argparse.Namespace(run_id="local-test", repo=None, sha=None))
    return seen


@pytest.mark.req('R2')
def test_failure_log_comes_from_the_sandbox(monkeypatch, tmp_path):
    repo = _repo(tmp_path / "repo", "assert 1 + 1 == 3")
    state = _run(monkeypatch, tmp_path, repo)
    assert "1 failed" in state["raw_log"]
    assert "test_add" in state["raw_log"]
    assert not (repo / "ran_here.txt").exists(), "the repository's test ran on the host"


def test_passing_tests_mean_nothing_to_fix(monkeypatch, tmp_path):
    repo = _repo(tmp_path / "repo", "assert 1 + 1 == 2")
    with pytest.raises(SystemExit) as stop:
        _run(monkeypatch, tmp_path, repo)
    assert stop.value.code == 0
    assert not (repo / "ran_here.txt").exists()
