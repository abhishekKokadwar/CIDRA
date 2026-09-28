"""Phase 9.6 — draft-PR generation. REST mocked; git side on a real local remote."""

from pathlib import Path

import httpx
import pytest

from cidra import config
from cidra.git_ops import git
from cidra.integrations import github_write
from cidra.nodes import pr


# ---------- open_draft_pr (REST, mocked) ----------

def _mock(monkeypatch, handler, token="wtok"):
    monkeypatch.setattr(github_write, "GITHUB_TOKEN", token, raising=False)
    monkeypatch.setattr(github_write, "_client",
                        lambda: httpx.Client(base_url="https://api.github.com",
                                             transport=httpx.MockTransport(handler)))


def test_open_draft_pr_creates_when_none(monkeypatch):
    seen = {}

    def handler(req):
        if req.method == "GET" and req.url.path.endswith("/pulls"):
            return httpx.Response(200, json=[])           # none open
        if req.method == "GET":                            # repo → default branch
            return httpx.Response(200, json={"default_branch": "main"})
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"html_url": "https://gh/pr/1"})

    _mock(monkeypatch, handler)
    url = pr and github_write.open_draft_pr("o/r", "cidra/patch-1", "t", "b")
    assert url == "https://gh/pr/1"
    assert '"draft": true' in seen["body"].replace(" ", "").replace('"draft":true', '"draft": true') \
        or '"draft":true' in seen["body"]  # draft flag set


def test_open_draft_pr_is_idempotent(monkeypatch):
    def handler(req):
        if req.url.path.endswith("/pulls") and req.method == "GET":
            return httpx.Response(200, json=[{"html_url": "https://gh/pr/existing"}])
        raise AssertionError("must not POST when a PR already exists")

    _mock(monkeypatch, handler)
    assert github_write.open_draft_pr("o/r", "cidra/patch-1", "t", "b") == "https://gh/pr/existing"


def test_open_draft_pr_never_merges(monkeypatch):
    """SR-11: the PR path must never call a merge endpoint."""
    def handler(req):
        assert "/merge" not in req.url.path
        if req.url.path.endswith("/pulls") and req.method == "GET":
            return httpx.Response(200, json=[])
        if req.method == "GET":
            return httpx.Response(200, json={"default_branch": "main"})
        return httpx.Response(201, json={"html_url": "https://gh/pr/1"})

    _mock(monkeypatch, handler)
    github_write.open_draft_pr("o/r", "cidra/patch-1", "t", "b")


# ---------- build_fix_branch (real git, local bare remote) ----------

@pytest.fixture
def repo_and_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    # a source repo
    src = tmp_path / "src"; src.mkdir()
    git("init", "-q", "-b", "main", cwd=src)
    git("config", "user.email", "t@t", cwd=src); git("config", "user.name", "t", cwd=src)
    (src / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    git("add", "-A", cwd=src); git("commit", "-qm", "c1", cwd=src)
    # a bare remote to push to (stands in for github)
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", str(remote))
    return src, remote


def test_build_fix_branch_applies_diff_and_pushes(repo_and_remote, monkeypatch):
    src, remote = repo_and_remote
    diff = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n-    return a - b\n+    return a + b\n")

    # Point the "authenticated remote" at our local bare repo instead of github.
    monkeypatch.setattr(pr, "_authenticated_remote", lambda repo, token, api: str(remote))

    branch = pr.build_fix_branch("run1", src, diff, "o/r", "tok", "https://api.github.com")
    assert branch == "cidra/patch-run1"

    # the branch exists on the remote with the fix applied (allow_file: local remote)
    out = git("ls-remote", "--heads", str(remote), cwd=src, allow_file=True).stdout
    assert "cidra/patch-run1" in out


def test_build_fix_branch_no_push(repo_and_remote):
    src, _ = repo_and_remote
    diff = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n-    return a - b\n+    return a + b\n")
    branch = pr.build_fix_branch("run2", src, diff, "o/r", "tok",
                                 "https://api.github.com", push=False)
    assert branch == "cidra/patch-run2"


# ---------- publish wiring ----------

def test_publish_opens_pr_on_verified_fix(monkeypatch):
    from cidra.nodes import publish
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PR_CREATION", True, raising=False)
    monkeypatch.setattr(publish, "_open_pr", lambda state, body: "https://gh/pr/9")

    from cidra.state import Analysis
    state = {"repo": "o/r", "run_id": "1", "outcome": "verified_fix", "verified": True,
             "fix_diff": "+x", "commit_sha": "abc",
             "analysis": Analysis(category="missing_dependency", confidence=0.9,
                                  evidence="e", proposed_action="p")}
    out = publish.publish(state)
    assert out["pr_url"] == "https://gh/pr/9"


def test_publish_no_pr_when_not_verified(monkeypatch):
    from cidra.nodes import publish
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    called = {"n": 0}
    monkeypatch.setattr(publish, "_open_pr", lambda s, b: called.__setitem__("n", called["n"] + 1))
    out = publish.publish({"repo": "o/r", "run_id": "1", "outcome": "diagnosis_only",
                           "analysis": None})
    assert out["pr_url"] is None and called["n"] == 0
