"""Phase 9.5 / SEC-04 — git-hook & config command-execution containment (SR-16/17).

Builds a real hostile repo (post-checkout hook + core.fsmonitor + malicious alias)
and drives it through the hardened checkout + ordinary git ops. The canary must
never fire and no .git may reach the sandbox tree."""

from pathlib import Path

import pytest

from cidra import config
from cidra.git_ops import git
from cidra.nodes import checkout


@pytest.fixture
def hostile_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    canary = tmp_path / "CIDRA_SEC04_CANARY"
    src = tmp_path / "evil"; src.mkdir()
    git("init", "-q", cwd=src)
    git("config", "user.email", "t@t", cwd=src); git("config", "user.name", "t", cwd=src)
    (src / "a.txt").write_text("x")
    git("add", "-A", cwd=src); git("commit", "-qm", "c1", cwd=src)
    # plant every vector
    hook = src / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{canary}'\n"); hook.chmod(0o755)
    git("config", "core.fsmonitor", f"touch '{canary}'", cwd=src)
    git("config", "alias.st", f"!touch '{canary}'; status", cwd=src)
    return src, canary


def test_checkout_does_not_fire_hook_or_fsmonitor(hostile_repo):
    src, canary = hostile_repo
    tree = checkout.prepare_checkout("sec04", src)
    assert not canary.exists()             # SR-16: no hook/fsmonitor ran
    assert not (tree / ".git").exists()    # SR-17: no .git in the sandbox tree


def test_ordinary_git_ops_on_hostile_repo_are_inert(hostile_repo):
    src, canary = hostile_repo
    git("status", cwd=src)
    git("log", "--oneline", cwd=src)
    git("diff", "HEAD", cwd=src, check=False)
    assert not canary.exists()             # fsmonitor never executes its command


def test_neutralize_flags_cover_known_vectors():
    from cidra.git_ops import hardened_flags
    flags = " ".join(hardened_flags())
    for key in ("core.fsmonitor=", "core.sshCommand=", "diff.external="):
        assert key in flags
