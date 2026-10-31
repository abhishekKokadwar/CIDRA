"""The model-key proxy (ROADMAP M7). Runs in its own container; stdlib only.

A coding agent runs next to repository code it does not control, so the model
key must not be where that code can read it. The key lives here, in a container
no repository code runs in. The agent's container sits on a network whose only
other member is this proxy (runner.AgentNetwork), so the proxy is its one way
out: it forwards model calls and nothing else, puts the real key on them, and
stops after a per-run number of requests. For each model call it prints one
line of token counts read from the reply (usage_of), so the run's cost is
measured here rather than taken from the agent's own report.
"""

import http.client
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080
ALLOWED_PATHS = ("/v1/messages", "/v1/messages/count_tokens")
# The SDKs mark a beta call with this query; anything else is refused. The
# forwarded URL is built from these constants, never from what the caller sent.
ALLOWED_QUERIES = {"": "", "beta=true": "?beta=true"}
# Never forwarded from the agent: its own credentials (replaced below) and
# headers that describe this hop. Without accept-encoding the reply is plain.
_DROP_REQUEST = {"host", "x-api-key", "authorization", "proxy-authorization",
                 "content-length", "connection", "accept-encoding"}
_DROP_RESPONSE = {"connection", "transfer-encoding", "keep-alive", "content-length"}
# A subscription token is an OAuth credential: the API takes it with this beta.
OAUTH_BETA = "oauth-2025-04-20"
USAGE_PREFIX = "CIDRA_USAGE "


def usage_of(reply: bytes) -> dict | None:
    """Token counts in a model reply, streamed (server-sent events) or whole.
    A stream states input tokens when it starts and the output total at its end."""
    found: dict = {}
    events = [line[5:].strip() for line in reply.splitlines() if line.startswith(b"data:")]
    for raw in events or [reply]:
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        message = event.get("message", event) if isinstance(event, dict) else {}
        usage = {**(message.get("usage") or {}), **(event.get("usage") or {})} if isinstance(message, dict) else {}
        if message.get("model"):
            found["model"] = message["model"]
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            if isinstance(usage.get(key), int):
                found[key] = usage[key]
    return found if "output_tokens" in found else None


def make_handler(upstream: str, key: str, auth: str = "x-api-key", max_requests: int = 50):
    """`auth` is "x-api-key" for a console API key, "bearer" for a token."""
    target = urllib.parse.urlsplit(upstream)
    lock, used = threading.Lock(), [0]
    # ponytail: caps requests, not tokens; count usage from the replies if a
    # request cap proves too coarse for the spend limit.

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # requests carry source code and logs: never written anywhere

        def _refuse(self, status: int, message: str) -> None:
            body = json.dumps({"type": "error", "error": {"type": "cidra_proxy", "message": message}}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._refuse(403, "only model calls are forwarded")

        def do_POST(self):
            # Read the request whole before any answer: a refusal sent while the
            # caller is still sending is a dropped connection, not a 403 or 429.
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            asked = urllib.parse.urlsplit(self.path)
            if asked.path not in ALLOWED_PATHS or asked.query not in ALLOWED_QUERIES:
                return self._refuse(403, f"only model calls are forwarded, not {asked.path}")
            path = ALLOWED_PATHS[ALLOWED_PATHS.index(asked.path)]
            with lock:
                if used[0] >= max_requests:
                    return self._refuse(429, f"this run's limit of {max_requests} model requests is reached")
                used[0] += 1
            headers = {k.lower(): v for k, v in self.headers.items() if k.lower() not in _DROP_REQUEST}
            if auth == "bearer":
                headers["authorization"] = f"Bearer {key}"
                betas = [b for b in headers.get("anthropic-beta", "").split(",") if b.strip()]
                headers["anthropic-beta"] = ",".join([*betas, OAUTH_BETA])
            else:
                headers["x-api-key"] = key
            conn_class = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
            conn = conn_class(target.hostname, target.port, timeout=600)
            try:
                conn.request("POST", target.path.rstrip("/") + path + ALLOWED_QUERIES[asked.query], body, headers)
                reply = conn.getresponse()
            except OSError as e:
                conn.close()
                return self._refuse(502, f"model endpoint unreachable: {type(e).__name__}")
            try:
                self.send_response(reply.status)
                for k, v in reply.getheaders():
                    if k.lower() not in _DROP_RESPONSE:
                        self.send_header(k, v)
                self.end_headers()
                # Relayed as it arrives, so a streamed reply streams; the
                # connection closing marks its end (HTTP/1.0).
                seen = []
                while chunk := reply.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    seen.append(chunk)
            finally:
                conn.close()
            if path == "/v1/messages" and (usage := usage_of(b"".join(seen))):
                print(USAGE_PREFIX + json.dumps(usage), flush=True)

    return Handler


def main() -> None:
    handler = make_handler(os.environ["CIDRA_PROXY_UPSTREAM"], os.environ["CIDRA_PROXY_KEY"],
                           os.environ.get("CIDRA_PROXY_AUTH", "x-api-key"),
                           int(os.environ.get("CIDRA_PROXY_MAX_REQUESTS", "50")))
    ThreadingHTTPServer(("0.0.0.0", PORT), handler).serve_forever()


if __name__ == "__main__":
    main()
