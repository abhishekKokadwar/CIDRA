"""Phase 9.2 — isolated, .git-free per-run checkout. Real git on temp repos."""

from pathlib import Path

import pytest

from cidra import config
from cidra.git_ops import git
from cidra.nodes import checkout


@pytest.fixture
def src_repo(tmp_path):
    """A source repo with two commits, so we can check out an older one."""
    r = tmp_path / "src"
    r.mkdir()
    git("init", "-q", cwd=r)
    git("config", "user.email", "t@t", cwd=r)
    git("config", "user.name", "t", cwd=r)
    (r / "app.py").write_text("v1")
    git("add", "-A", cwd=r); git("commit", "-qm", "c1", cwd=r)
    first = git("rev-parse", "HEAD", cwd=r).stdout.strip()
    (r / "app.py").write_text("v2")
    git("add", "-A", cwd=r); git("commit", "-qm", "c2", cwd=r)
    return r, first


@pytest.fixture(autouse=True)
def worktrees_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))


def test_checkout_produces_a_tree(src_repo):
    r, _ = src_repo
    dest = checkout.prepare_checkout("run1", r)
    assert (dest / "app.py").exists()
    assert (dest / "app.py").read_text() == "v2"  # default = latest


def test_checkout_strips_dot_git(src_repo):
    """SR-17: the tree handed to the sandbox has no .git."""
    r, _ = src_repo
    dest = checkout.prepare_checkout("run1", r)
    assert not (dest / ".git").exists()


def test_checkout_honors_commit_sha(src_repo):
    r, first = src_repo
    dest = checkout.prepare_checkout("run1", r, commit_sha=first)
    assert (dest / "app.py").read_text() == "v1"  # older commit


def test_two_runs_are_isolated(src_repo):
    """Concurrent-safe: distinct run_ids get distinct dirs; editing one never
    touches the other."""
    r, _ = src_repo
    d1 = checkout.prepare_checkout("runA", r)
    d2 = checkout.prepare_checkout("runB", r)
    assert d1 != d2
    (d1 / "app.py").write_text("mutated-A")
    assert (d2 / "app.py").read_text() == "v2"  # B untouched


def test_reprepare_is_idempotent(src_repo):
    r, _ = src_repo
    d1 = checkout.prepare_checkout("run1", r)
    (d1 / "stale.txt").write_text("old")
    d2 = checkout.prepare_checkout("run1", r)  # same run_id, fresh tree
    assert d1 == d2
    assert not (d2 / "stale.txt").exists()  # stale file gone


def test_remove_checkout(src_repo):
    r, _ = src_repo
    dest = checkout.prepare_checkout("run1", r)
    checkout.remove_checkout("run1")
    assert not Path(dest).exists()
