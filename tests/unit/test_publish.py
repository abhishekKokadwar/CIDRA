"""Phase 6.3 — publish node wiring."""

from cidra.nodes import publish
from cidra.state import Analysis

STATE = {
    "repo": "o/r", "run_id": "1", "outcome": "verified_fix", "verified": True,
    "fix_diff": "+requests==2.31.0",
    "analysis": Analysis(category="missing_dependency", confidence=0.9,
                         evidence="x", proposed_action="y"),
}


def test_dry_run_without_issue_number(monkeypatch):
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)  # token present…
    out = publish.publish(dict(STATE))  # …but no issue_number ⇒ still dry-run
    assert out["comment_url"] is None
    assert "```diff" in out["final_output"]  # still rendered


def test_dry_run_when_no_token(monkeypatch):
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "", raising=False)
    out = publish.publish({**STATE, "issue_number": 7})
    assert out["comment_url"] is None


def test_posts_when_issue_and_token_present(monkeypatch):
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    posted = {}

    def fake_post(repo, issue, body):
        posted.update(repo=repo, issue=issue, body=body)
        return "https://gh/c/1"

    import cidra.integrations.github_write as gw
    monkeypatch.setattr(gw, "post_or_update_comment", fake_post)

    out = publish.publish({**STATE, "issue_number": 7})
    assert out["comment_url"] == "https://gh/c/1"
    assert posted["issue"] == 7 and "```diff" in posted["body"]


def test_explicit_dry_run_flag_blocks_posting(monkeypatch):
    import cidra.config as cfg
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok", raising=False)
    out = publish.publish({**STATE, "issue_number": 7, "dry_run": True})
    assert out["comment_url"] is None
