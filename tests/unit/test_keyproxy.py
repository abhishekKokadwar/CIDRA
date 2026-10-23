"""The model-key proxy forwards model calls only, with the real key in place of
whatever the caller sent, and stops at the run's request limit (ROADMAP M7).
In-process: the proxy and a stand-in for the model endpoint on local ports."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cidra.sandbox.keyproxy import make_handler

pytestmark = pytest.mark.req("M7-KEY-PROXY")

KEY = "sk-real-key-held-by-the-proxy"


class Upstream(BaseHTTPRequestHandler):
    """Says what it received, except the key itself."""
    seen: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Upstream.seen.append({"path": self.path, "x-api-key": self.headers.get("x-api-key"),
                              "authorization": self.headers.get("authorization"), "body": body,
                              "beta": self.headers.get("anthropic-beta")})
        reply = b'data: {"type": "message_start"}\n\ndata: {"type": "message_stop"}\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(reply)


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def proxy():
    Upstream.seen = []
    upstream = _serve(Upstream)
    servers = []

    def start(**kw):
        servers.append(_serve(make_handler(f"http://127.0.0.1:{upstream.server_port}", KEY, **kw)))
        return f"http://127.0.0.1:{servers[-1].server_port}"
    yield start
    for s in [upstream, *servers]:
        s.shutdown()


def _post(url, path, headers=None):
    req = urllib.request.Request(url + path, data=b'{"model": "m"}', method="POST",
                                 headers={"x-api-key": "what-the-agent-sent", "anthropic-beta": "b1", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_a_model_call_reaches_the_endpoint_with_the_real_key_only(proxy):
    status, body = _post(proxy(), "/v1/messages?beta=true", {"Authorization": "Bearer agent-token"})
    assert status == 200 and b"message_stop" in body  # the streamed reply arrives whole
    seen = Upstream.seen[-1]
    assert seen["path"] == "/v1/messages?beta=true" and seen["body"] == b'{"model": "m"}'
    assert seen["x-api-key"] == KEY and seen["authorization"] is None and seen["beta"] == "b1"


def test_a_token_goes_as_a_bearer_credential(proxy):
    _post(proxy(auth="bearer"), "/v1/messages")
    assert Upstream.seen[-1]["authorization"] == f"Bearer {KEY}" and Upstream.seen[-1]["x-api-key"] is None


def test_anything_but_a_model_call_is_refused(proxy):
    url = proxy()
    assert _post(url, "/v1/files")[0] == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(url + "/v1/models", timeout=5)
    assert e.value.code == 403 and Upstream.seen == []


def test_the_run_stops_at_its_request_limit(proxy):
    url = proxy(max_requests=2)
    assert [_post(url, "/v1/messages")[0] for _ in range(3)] == [200, 200, 429]
    assert len(Upstream.seen) == 2


def test_an_unreachable_endpoint_is_a_502_not_a_hang():
    server = _serve(make_handler("http://127.0.0.1:9", KEY))
    try:
        status, body = _post(f"http://127.0.0.1:{server.server_port}", "/v1/messages")
        assert status == 502 and KEY not in body.decode() and "unreachable" in json.loads(body)["error"]["message"]
    finally:
        server.shutdown()
