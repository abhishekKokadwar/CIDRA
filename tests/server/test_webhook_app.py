"""Phase 7.4 — FastAPI webhook receiver. TestClient, mocked graph."""

import json

import pytest
from fastapi.testclient import TestClient

from cidra import config
from cidra.server import app as appmod
from cidra.server.idempotency import IdempotencyStore
from cidra.server.security import sign

SECRET = "hooksecret"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEBHOOK_SECRET", SECRET, raising=False)
    monkeypatch.setattr(appmod, "_store", IdempotencyStore(tmp_path / "i.db"))
    dispatched = []
    monkeypatch.setattr(appmod, "process_job", lambda job: dispatched.append(job))
    c = TestClient(appmod.app)
    c.dispatched = dispatched
    return c


def _body(conclusion="failure", run_id=999, prs=(("number", 42),)):
    pr = [dict(prs)] if prs else []
    return json.dumps({
        "action": "completed",
        "repository": {"full_name": "helpmecode69/cidra-practice"},
        "workflow_run": {"id": run_id, "head_sha": "abc123",
                         "conclusion": conclusion, "pull_requests": pr},
    }).encode()


def _post(client, body, event="workflow_run", secret=SECRET):
    return client.post("/webhook", content=body, headers={
        "X-Hub-Signature-256": sign(body, secret),
        "X-GitHub-Event": event,
    })


def test_health():
    assert TestClient(appmod.app).get("/").json()["ok"] is True


def test_valid_failure_accepted_and_dispatched(client):
    r = _post(client, _body())
    assert r.status_code == 200 and "accepted" in r.text
    assert len(client.dispatched) == 1
    assert client.dispatched[0].run_id == "999" and client.dispatched[0].issue_number == 42


def test_bad_signature_401_and_no_dispatch(client):
    body = _body()
    r = client.post("/webhook", content=body, headers={
        "X-Hub-Signature-256": sign(body, "wrong"), "X-GitHub-Event": "workflow_run"})
    assert r.status_code == 401
    assert client.dispatched == []


def test_missing_signature_401(client):
    body = _body()
    r = client.post("/webhook", content=body, headers={"X-GitHub-Event": "workflow_run"})
    assert r.status_code == 401


def test_success_conclusion_204(client):
    r = _post(client, _body(conclusion="success"))
    assert r.status_code == 204
    assert client.dispatched == []


def test_wrong_event_204(client):
    r = _post(client, _body(), event="push")
    assert r.status_code == 204


def test_duplicate_delivery_is_noop(client):
    r1 = _post(client, _body())
    r2 = _post(client, _body())  # same run_id + sha
    assert r1.status_code == 200 and "accepted" in r1.text
    assert r2.status_code == 200 and "duplicate" in r2.text
    assert len(client.dispatched) == 1  # engine invoked once, not twice


def test_signature_checked_before_parse(client):
    """A malformed body with a bad signature is 401, never a 400 parse error —
    proving verification runs first (no body parsing on an unauthenticated req)."""
    r = client.post("/webhook", content=b"not json", headers={
        "X-Hub-Signature-256": sign(b"other", SECRET), "X-GitHub-Event": "workflow_run"})
    assert r.status_code == 401
