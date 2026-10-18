"""A run with no pull request still posts its report, on the failing commit
(KNOWN_GAPS G-08), and a refused write says which permission is missing."""

import httpx
import pytest

import cidra.config as cfg
from cidra.integrations import github_write
from cidra.nodes import publish
from cidra.nodes.report import _MARKER

pytestmark = pytest.mark.req("M4-PUBLISH")


def _mock(monkeypatch, handler):
    monkeypatch.setattr(github_write, "GITHUB_TOKEN", "wtok", raising=False)
    monkeypatch.setattr(github_write, "_client", lambda: httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))


def _state(**extra):
    return {"repo": "o/r", "run_id": "1", "outcome": "diagnosis_only", "commit_sha": "c0ffee1234", "analysis": None, **extra}


def test_commit_comment_is_posted_then_updated_not_duplicated(monkeypatch):
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path))
        if req.method == "GET":
            existing = [{"id": 5, "body": f"{_MARKER} old"}] if len(seen) > 2 else []
            return httpx.Response(200, json=existing)
        return httpx.Response(200, json={"html_url": "https://gh/commit/c#1"})

    _mock(monkeypatch, handler)
    body = f"{_MARKER}\nreport"
    assert github_write.post_or_update_commit_comment("o/r", "c0ffee", body) == "https://gh/commit/c#1"
    github_write.post_or_update_commit_comment("o/r", "c0ffee", body)
    assert seen == [("GET", "/repos/o/r/commits/c0ffee/comments"), ("POST", "/repos/o/r/commits/c0ffee/comments"),
                    ("GET", "/repos/o/r/commits/c0ffee/comments"), ("PATCH", "/repos/o/r/comments/5")]


def test_a_branch_push_with_no_pr_comments_on_the_commit(monkeypatch):
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    posted = []
    monkeypatch.setattr(github_write, "post_or_update_commit_comment",
                        lambda repo, sha, body: posted.append((repo, sha)) or "https://gh/commit")
    out = publish.publish(_state())
    assert posted == [("o/r", "c0ffee1234")] and out["comment_url"] == "https://gh/commit"
    assert publish.publish(_state(commit_sha="HEAD"))["comment_url"] is None  # a local run has no real commit


def test_a_403_names_the_missing_permission_and_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def refused(*args):
        raise httpx.HTTPStatusError("403", request=httpx.Request("POST", "https://x"),
                                    response=httpx.Response(403))

    monkeypatch.setattr(github_write, "post_or_update_comment", refused)
    out = publish.publish(_state(issue_number=7))
    assert out["comment_url"] is None
    assert out["publish_errors"] == ["GitHub refused to comment on the pull request (403). Give the workflow job "
                                     "that runs CIDRA `permissions:` pull-requests: write."]
    assert "CIDRA could not publish:** GitHub refused to comment" in summary.read_text(encoding="utf-8")


def test_a_failed_pr_step_falls_back_to_a_commit_comment_and_says_why(monkeypatch):
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PR_CREATION", True, raising=False)

    def refused(state, body):
        raise httpx.HTTPStatusError("403", request=httpx.Request("POST", "https://x"), response=httpx.Response(403))

    monkeypatch.setattr(publish, "_open_pr", refused)
    monkeypatch.setattr(github_write, "post_or_update_commit_comment", lambda repo, sha, body: "https://gh/commit")
    out = publish.publish(_state(outcome="verified_fix", verified=True, fix_diff="+x"))
    assert out["pr_url"] is None and out["comment_url"] == "https://gh/commit"
    assert "open a draft pull request (403)" in out["publish_errors"][0]
    assert "contents: write, pull-requests: write" in out["publish_errors"][0]
