"""Phase 7.3 — webhook event parsing, filtering, PR resolution."""

import httpx

from cidra.server import events
from cidra.server.events import parse_event, resolve_issue_number, WebhookJob


def _payload(action="completed", conclusion="failure", prs=None):
    return {
        "action": action,
        "repository": {"full_name": "helpmecode69/cidra-practice"},
        "workflow_run": {
            "id": 999, "head_sha": "abc123",
            "conclusion": conclusion,
            "pull_requests": prs if prs is not None else [],
        },
    }


def test_failure_completed_is_actionable():
    job = parse_event("workflow_run", _payload(prs=[{"number": 42}]))
    assert job == WebhookJob("helpmecode69/cidra-practice", "999", "abc123", 42)


def test_success_is_skipped():
    assert parse_event("workflow_run", _payload(conclusion="success")) is None


def test_non_completed_action_skipped():
    assert parse_event("workflow_run", _payload(action="requested")) is None


def test_wrong_event_type_skipped():
    assert parse_event("push", _payload()) is None
    assert parse_event(None, _payload()) is None


def test_missing_identity_skipped():
    p = _payload(prs=[{"number": 42}])
    del p["workflow_run"]["head_sha"]
    assert parse_event("workflow_run", p) is None


def test_no_pr_in_payload_gives_none_issue():
    job = parse_event("workflow_run", _payload(prs=[]))
    assert job.issue_number is None  # ⇒ dry-run unless SHA lookup finds one


def test_resolve_returns_payload_number_without_lookup(monkeypatch):
    job = WebhookJob("o/r", "1", "sha", 7)
    # Must NOT touch the network when the number is already known.
    monkeypatch.setattr(events, "_client_unused", None, raising=False)
    assert resolve_issue_number(job) == 7


def test_resolve_by_sha_for_fork_pr(monkeypatch):
    job = WebhookJob("o/r", "1", "deadbeef", None)

    def handler(req):
        assert "/commits/deadbeef/pulls" in str(req.url)
        return httpx.Response(200, json=[{"state": "open", "number": 55}])

    import cidra.integrations.github as gh
    monkeypatch.setattr(gh, "GITHUB_TOKEN_RO", "ro", raising=False)
    monkeypatch.setattr(gh, "_client",
                        lambda: httpx.Client(base_url="https://api.github.com",
                                             transport=httpx.MockTransport(handler)))
    assert resolve_issue_number(job) == 55


def test_resolve_returns_none_when_no_pr(monkeypatch):
    job = WebhookJob("o/r", "1", "deadbeef", None)
    import cidra.integrations.github as gh
    monkeypatch.setattr(gh, "GITHUB_TOKEN_RO", "ro", raising=False)
    monkeypatch.setattr(gh, "_client",
                        lambda: httpx.Client(base_url="https://api.github.com",
                                             transport=httpx.MockTransport(
                                                 lambda req: httpx.Response(200, json=[]))))
    assert resolve_issue_number(job) is None


def test_resolve_swallows_network_error(monkeypatch):
    job = WebhookJob("o/r", "1", "deadbeef", None)

    def boom(req):
        raise httpx.ConnectError("down")

    import cidra.integrations.github as gh
    monkeypatch.setattr(gh, "GITHUB_TOKEN_RO", "ro", raising=False)
    monkeypatch.setattr(gh, "_client",
                        lambda: httpx.Client(base_url="https://api.github.com",
                                             transport=httpx.MockTransport(boom)))
    assert resolve_issue_number(job) is None  # dry-run, not a crash
