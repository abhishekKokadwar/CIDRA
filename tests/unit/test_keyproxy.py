"""The model-key proxy forwards model calls only, with the real key in place of
whatever the caller sent, and stops at the run's request limit (ROADMAP M7).
In-process: the proxy and a stand-in for the model endpoint on local ports."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cidra.sandbox.keyproxy import OAUTH_BETA, USAGE_PREFIX, make_handler, usage_of

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
        reply = (b'data: {"type": "message_start", "message": {"model": "claude-x", "usage": {"input_tokens": 12, '
                 b'"cache_read_input_tokens": 100, "cache_creation_input_tokens": 7, "output_tokens": 1}}}\n\n'
                 b'data: {"type": "message_delta", "usage": {"output_tokens": 34}}\n\n'
                 b'data: {"type": "message_stop"}\n\n')
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
    seen = Upstream.seen[-1]
    assert seen["authorization"] == f"Bearer {KEY}" and seen["x-api-key"] is None
    assert seen["beta"] == f"b1,{OAUTH_BETA}"  # the agent's betas kept, the token's added


def test_each_model_calls_tokens_are_recorded_from_the_reply(proxy, capsys):
    _post(proxy(), "/v1/messages")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith(USAGE_PREFIX)]
    assert [json.loads(ln[len(USAGE_PREFIX):]) for ln in lines] == [
        {"model": "claude-x", "input_tokens": 12, "output_tokens": 34,
         "cache_read_input_tokens": 100, "cache_creation_input_tokens": 7}]


def test_usage_is_read_from_a_whole_reply_and_absent_from_an_error():
    whole = b'{"model": "m", "usage": {"input_tokens": 3, "output_tokens": 4}}'
    assert usage_of(whole) == {"model": "m", "input_tokens": 3, "output_tokens": 4}
    assert usage_of(b'{"type": "error", "error": {"message": "x"}}') is None


def test_anything_but_a_model_call_is_refused(proxy):
    url = proxy()
    assert _post(url, "/v1/files")[0] == 403
    assert _post(url, "/v1/messages?x=@evil.example/")[0] == 403  # the URL forwarded is built from constants
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(url + "/v1/models", timeout=5)
    assert e.value.code == 403 and Upstream.seen == []


def test_the_run_stops_at_its_request_limit(proxy):
    url = proxy(max_requests=2)
    assert [_post(url, "/v1/messages")[0] for _ in range(3)] == [200, 200, 429]
    assert len(Upstream.seen) == 2


def test_a_refusal_arrives_as_a_status_even_while_a_large_request_is_sent(proxy):
    # A prompt with source code runs to megabytes. Refusing before reading it
    # dropped the connection on Windows: the caller saw an error, not the 403/429.
    url = proxy(max_requests=0)
    big = b'{"model": "m", "pad": "' + b"x" * 4_000_000 + b'"}'
    for path, status in (("/v1/files", 403), ("/v1/messages", 429)):
        req = urllib.request.Request(url + path, data=big, method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == status
    assert Upstream.seen == []


def test_an_unreachable_endpoint_is_a_502_not_a_hang():
    server = _serve(make_handler("http://127.0.0.1:9", KEY))
    try:
        status, body = _post(f"http://127.0.0.1:{server.server_port}", "/v1/messages")
        assert status == 502 and KEY not in body.decode() and "unreachable" in json.loads(body)["error"]["message"]
    finally:
        server.shutdown()
