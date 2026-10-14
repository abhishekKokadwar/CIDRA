"""Webhook mode fetches the failing commit itself, and the token stays out of every file and command line."""

import base64
import subprocess
from pathlib import Path

import pytest

from cidra import config, git_ops
from cidra.git_ops import git
from cidra.nodes import checkout, environment, publish

TOKEN = "ghs_planted_read_token"


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A local repository standing in for github.com/<repo>, with two commits."""
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.setattr(config, "GITHUB_TOKEN_RO", TOKEN)
    r = tmp_path / "remote"; r.mkdir()
    git("init", "-q", cwd=r)
    git("config", "user.email", "t@t", cwd=r); git("config", "user.name", "t", cwd=r)
    (r / "app.py").write_text("failing\n")
    git("add", "-A", cwd=r); git("commit", "-qm", "failing", cwd=r)
    failing = git("rev-parse", "HEAD", cwd=r).stdout.strip()
    (r / "app.py").write_text("later\n")
    git("commit", "-qam", "later", cwd=r)
    monkeypatch.setattr(checkout, "remote_url", lambda repo: str(r))
    return failing


@pytest.fixture
def calls(monkeypatch):
    seen = []
    real = subprocess.run

    def spy(cmd, *args, **kwargs):
        seen.append((list(cmd), dict(kwargs.get("env") or {})))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(git_ops.subprocess, "run", spy)
    return seen


def _secrets():
    return (TOKEN, base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode())


def test_webhook_run_checks_out_the_failing_commit(remote):
    out = environment.checkout_commit({"run_id": "w1", "repo": "o/r", "commit_sha": remote})
    tree = Path(out["source_dir"])
    assert (tree / "app.py").read_text() == "failing\n"
    assert not (tree / ".git").exists()


def test_the_token_is_never_on_a_command_line_or_on_disk(remote, calls):
    out = environment.checkout_commit({"run_id": "w1", "repo": "o/r", "commit_sha": remote})
    for argv, _ in calls:
        assert not any(s in " ".join(argv) for s in _secrets()), argv
    fetches = [env for argv, env in calls if "fetch" in argv]
    assert len(fetches) == 1 and _secrets()[1] in fetches[0].get("GIT_CONFIG_VALUE_0", "")
    for root in (Path(out["repo_dir"]), Path(out["source_dir"])):
        for f in root.rglob("*"):
            if f.is_file():
                data = f.read_bytes()
                assert not any(s.encode() in data for s in _secrets()), f


def test_cleanup_removes_the_fetched_source(remote):
    out = environment.checkout_commit({"run_id": "w1", "repo": "o/r", "commit_sha": remote})
    publish.cleanup({"run_id": "w1"})
    assert not Path(out["repo_dir"]).exists() and not Path(out["source_dir"]).exists()
