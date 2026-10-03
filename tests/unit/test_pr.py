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


def test_build_fix_branch_with_the_default_relative_worktree_root(repo_and_remote, monkeypatch, tmp_path):
    # The default CIDRA_WORKTREE_ROOT is the relative "worktrees": the patch file
    # path must still resolve when git runs with cwd inside the clone.
    src, _ = repo_and_remote
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "WORKTREE_ROOT", "worktrees")
    diff = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n-    return a - b\n+    return a + b\n")
    assert pr.build_fix_branch("run3", src, diff, "o/r", "tok",
                               "https://api.github.com", push=False) == "cidra/patch-run3"


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


# ---------- the PR path after checkout_commit (regression: .git-stripped source) ----------

_FIX = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n-    return a - b\n+    return a + b\n")


def test_pr_branch_builds_after_checkout_commit(repo_and_remote, monkeypatch):
    """checkout_commit points source_dir at a tree with no .git; the PR path
    must still clone the real repo, not that tree."""
    from cidra.nodes import environment, publish
    src, remote = repo_and_remote
    monkeypatch.setattr(pr, "_authenticated_remote", lambda repo, token, api: str(remote))

    state = {"run_id": "run3", "repo": "o/r", "source_dir": str(src), "fix_diff": _FIX}
    state.update(environment.checkout_commit(state))
    assert not (Path(state["source_dir"]) / ".git").exists()  # sandbox tree
    assert state["repo_dir"] == str(src)                       # real repo kept

    pr.build_fix_branch("run3", publish._repo_dir(state), _FIX, "o/r", "tok",
                        "https://api.github.com")
    heads = git("ls-remote", "--heads", str(remote), cwd=src, allow_file=True).stdout
    assert "cidra/patch-run3" in heads


def test_existing_pr_branch_is_never_force_pushed(repo_and_remote, monkeypatch):
    src, remote = repo_and_remote
    monkeypatch.setattr(pr, "_authenticated_remote", lambda repo, token, api: str(remote))
    base = git("rev-parse", "HEAD", cwd=src).stdout.strip()

    # The contributor's branch has moved on since the failing commit.
    git("checkout", "-q", "-b", "feature", cwd=src)
    (src / "new.py").write_text("x = 1\n")
    git("add", "-A", cwd=src); git("commit", "-qm", "contributor work", cwd=src)
    git("push", "-q", str(remote), "feature:feature", cwd=src, allow_file=True)
    theirs = git("rev-parse", "HEAD", cwd=src).stdout.strip()

    with pytest.raises(Exception):  # non-fast-forward push is rejected
        pr.build_fix_branch("run4", src, _FIX, "o/r", "tok", "https://api.github.com",
                            base_sha=base, branch_name="feature")
    remote_head = git("ls-remote", str(remote), "refs/heads/feature", cwd=src,
                      allow_file=True).stdout.split()[0]
    assert remote_head == theirs  # their work is intact


def test_verified_fix_still_comments_when_pr_step_fails(monkeypatch):
    from cidra.nodes import publish
    import cidra.config as cfg
    import cidra.integrations.github_write as gw
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PR_CREATION", True, raising=False)
    monkeypatch.setattr(publish, "_apply_to_existing_pr", lambda state, body: None)
    monkeypatch.setattr(gw, "post_or_update_comment", lambda repo, issue, body: "https://gh/c/1")

    from cidra.state import Analysis
    out = publish.publish({
        "repo": "o/r", "run_id": "1", "outcome": "verified_fix", "verified": True,
        "fix_diff": "+x", "commit_sha": "abc", "issue_number": 7, "pr_branch": "feature",
        "analysis": Analysis(category="missing_dependency", confidence=0.9,
                             evidence="e", proposed_action="p")})
    assert out["pr_url"] is None and out["comment_url"] == "https://gh/c/1"
