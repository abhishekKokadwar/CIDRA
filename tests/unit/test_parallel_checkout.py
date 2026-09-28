"""Phase 9.4 — concurrent checkouts don't collide.

The Phase 9 goal: multiple repairs run on one host without a shared working tree.
This drives many checkouts concurrently and asserts each run's tree is its own —
edits in one are invisible to the others, and cleanup of one doesn't disturb
another. Proves the isolation layer without needing Docker."""

import concurrent.futures as cf
from pathlib import Path

import pytest

from cidra import config
from cidra.git_ops import git
from cidra.nodes import checkout


@pytest.fixture
def src_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    r = tmp_path / "src"; r.mkdir()
    git("init", "-q", cwd=r)
    git("config", "user.email", "t@t", cwd=r); git("config", "user.name", "t", cwd=r)
    (r / "app.py").write_text("base")
    git("add", "-A", cwd=r); git("commit", "-qm", "c1", cwd=r)
    return r


def _one_run(src, run_id):
    tree = checkout.prepare_checkout(run_id, src)
    # simulate a repair mutating this run's tree
    (tree / "app.py").write_text(f"patched-by-{run_id}")
    (tree / f"marker-{run_id}").write_text("x")
    return run_id, tree


def test_ten_concurrent_runs_are_isolated(src_repo):
    ids = [f"run{i}" for i in range(10)]
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        results = dict(ex.map(lambda rid: _one_run(src_repo, rid), ids))

    # distinct dirs
    assert len({str(p) for p in results.values()}) == len(ids)

    # each tree carries ONLY its own edits and marker
    for rid, tree in results.items():
        assert (tree / "app.py").read_text() == f"patched-by-{rid}"
        assert (tree / f"marker-{rid}").exists()
        for other in ids:
            if other != rid:
                assert not (tree / f"marker-{other}").exists()  # no cross-contamination


def test_cleanup_of_one_does_not_touch_another(src_repo):
    a = checkout.prepare_checkout("A", src_repo)
    b = checkout.prepare_checkout("B", src_repo)
    checkout.remove_checkout("A")
    assert not Path(a).exists()
    assert Path(b).exists() and (b / "app.py").exists()
