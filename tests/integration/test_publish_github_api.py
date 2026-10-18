"""publish over real HTTP against a local server that answers like GitHub's
REST API (G-08 and the 403 message). No Docker or token needed; the live
GitHub path is exercised by the ROADMAP M4 trials."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import cidra.config as cfg
from cidra.integrations import github_write
from cidra.nodes import publish

pytestmark = pytest.mark.req("M4-PUBLISH")


class FakeGitHub(BaseHTTPRequestHandler):
    comments: dict = {}
    refuse = False
    calls: list = []

    def _reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.calls.append(("GET", self.path.split("?")[0]))
        self._reply(200, [{"id": i, "body": b} for i, b in self.comments.items()])

    def _write(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))["body"]
        self.calls.append((self.command, self.path))
        if self.refuse:
            return self._reply(403, {"message": "Resource not accessible by integration"})
        cid = int(self.path.rsplit("/", 1)[1]) if self.command == "PATCH" else len(self.comments) + 1
        self.comments[cid] = body
        self._reply(200, {"html_url": f"https://github.test/o/r/commit/c0ffee#commitcomment-{cid}"})

    do_POST = do_PATCH = _write

    def log_message(self, *args):
        pass


@pytest.fixture
def github(monkeypatch):
    FakeGitHub.comments, FakeGitHub.refuse, FakeGitHub.calls = {}, False, []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(github_write, "GITHUB_API", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(github_write, "GITHUB_TOKEN", "wtok")
    monkeypatch.setattr(cfg, "GITHUB_TOKEN", "wtok")
    yield FakeGitHub
    server.shutdown()


STATE = {"repo": "o/r", "run_id": "1", "outcome": "diagnosis_only", "commit_sha": "c0ffee", "analysis": None}


def test_a_no_pr_run_comments_on_the_commit_and_a_rerun_updates_it(github):
    first = publish.publish(dict(STATE))
    second = publish.publish(dict(STATE))
    assert first["comment_url"].endswith("#commitcomment-1") and second["comment_url"].endswith("#commitcomment-1")
    assert len(github.comments) == 1 and "CIDRA" in github.comments[1]
    assert ("POST", "/repos/o/r/commits/c0ffee/comments") in github.calls
    assert ("PATCH", "/repos/o/r/comments/1") in github.calls


def test_a_refusal_from_github_becomes_the_permission_to_add(github):
    github.refuse = True
    out = publish.publish(dict(STATE))
    assert out["comment_url"] is None
    assert out["publish_errors"] == ["GitHub refused to comment on the commit (403). Give the workflow job that "
                                     "runs CIDRA `permissions:` contents: write."]
