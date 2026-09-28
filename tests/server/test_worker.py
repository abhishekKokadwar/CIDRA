"""Phase 7.5 — background graph dispatch."""

from cidra.server import worker
from cidra.server.events import WebhookJob

JOB = WebhookJob("o/r", "999", "abc123", 42)


def test_build_initial_state_maps_fields(monkeypatch):
    monkeypatch.setattr(worker, "resolve_issue_number", lambda j: j.issue_number)
    s = worker.build_initial_state(JOB)
    assert s == {"run_id": "999", "repo": "o/r", "commit_sha": "abc123", "issue_number": 42}


def test_process_job_invokes_graph_with_state(monkeypatch):
    monkeypatch.setattr(worker, "resolve_issue_number", lambda j: 42)
    seen = {}

    class FakeGraph:
        def invoke(self, state):
            seen.update(state)
            return {"outcome": "verified_fix", "comment_url": "https://gh/c/1"}

    import cidra.graph as g
    monkeypatch.setattr(g, "build_graph", lambda: FakeGraph())

    final = worker.process_job(JOB)
    assert seen["repo"] == "o/r" and seen["issue_number"] == 42
    assert final["comment_url"] == "https://gh/c/1"


def test_process_job_swallows_exceptions(monkeypatch):
    monkeypatch.setattr(worker, "resolve_issue_number", lambda j: None)

    class Boom:
        def invoke(self, state):
            raise RuntimeError("engine blew up")

    import cidra.graph as g
    monkeypatch.setattr(g, "build_graph", lambda: Boom())

    assert worker.process_job(JOB) is None  # logged, not raised
