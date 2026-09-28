"""Phase 9.3 — checkout_commit node wiring + cleanup."""

from pathlib import Path

import pytest

from cidra import config
from cidra.git_ops import git
from cidra.nodes import environment, publish


@pytest.fixture
def src_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    r = tmp_path / "src"; r.mkdir()
    git("init", "-q", cwd=r)
    git("config", "user.email", "t@t", cwd=r); git("config", "user.name", "t", cwd=r)
    (r / "app.py").write_text("v1")
    git("add", "-A", cwd=r); git("commit", "-qm", "c1", cwd=r)
    return r


def test_checkout_node_sets_isolated_source_dir(src_repo):
    out = environment.checkout_commit({"run_id": "r1", "source_dir": str(src_repo)})
    tree = Path(out["source_dir"])
    assert tree.exists() and (tree / "app.py").exists()
    assert not (tree / ".git").exists()          # SR-17
    assert tree != src_repo                       # isolated, not the original


def test_checkout_failure_sets_env_not_ready(src_repo):
    out = environment.checkout_commit({"run_id": "r1", "source_dir": "/no/such/path"})
    assert out["env_ready"] is False
    assert "checkout failed" in out["analysis_error"]


def test_cleanup_removes_checkout_dir(src_repo):
    out = environment.checkout_commit({"run_id": "r1", "source_dir": str(src_repo)})
    tree = Path(out["source_dir"])
    assert tree.exists()
    publish.cleanup({"run_id": "r1"})
    assert not tree.exists()                       # no leftover per-run tree


def test_prepare_sandbox_bails_if_checkout_failed(src_repo):
    # env_ready already False from a failed checkout: prepare must not mask it.
    out = environment.prepare_sandbox({"run_id": "r1", "env_ready": False})
    assert out == {}
