"""Phase 7.7 — replay tooling drives the real receiver correctly.

Uses the sample-payload path + TestClient (no GitHub, no Docker): proves the
script signs the exact bytes it sends and that the receiver accepts once and
no-ops on a duplicate. The full engine run is exercised separately when Docker
is up (see scripts/replay_delivery.py docstring)."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from cidra import config
from cidra.server import app as appmod
from cidra.server.idempotency import IdempotencyStore

replay = importlib.import_module("scripts.replay_delivery")
SECRET = "replaysecret"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEBHOOK_SECRET", SECRET, raising=False)
    monkeypatch.setattr(appmod, "_store", IdempotencyStore(tmp_path / "i.db"))
    monkeypatch.setattr(appmod, "process_job", lambda job: None)  # no engine
    return TestClient(appmod.app)


def _body():
    return json.dumps(
        replay._payload_sample("helpmecode69/cidra-practice", "999", "abc123", 42)
    ).encode()


def test_replay_body_is_signed_and_accepted(client, monkeypatch):
    monkeypatch.setenv("CIDRA_WEBHOOK_SECRET", SECRET)
    body = _body()
    r = client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "workflow_run",
        "X-Hub-Signature-256": replay.sign(body, SECRET),
    })
    assert r.status_code == 200 and "accepted" in r.text


def test_replay_wrong_secret_rejected(client):
    body = _body()
    r = client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "workflow_run",
        "X-Hub-Signature-256": replay.sign(body, "not-the-secret"),
    })
    assert r.status_code == 401


def test_replay_twice_is_idempotent(client):
    body = _body()
    hdr = {"X-GitHub-Event": "workflow_run",
           "X-Hub-Signature-256": replay.sign(body, SECRET)}
    r1 = client.post("/webhook", content=body, headers=hdr)
    r2 = client.post("/webhook", content=body, headers=hdr)
    assert r1.status_code == 200 and "accepted" in r1.text
    assert r2.status_code == 200 and "duplicate" in r2.text
