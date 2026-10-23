"""Repository code next to a coding agent cannot read the model key or get past
the proxy (ROADMAP M7). Real Docker: a stand-in model endpoint on the normal
bridge network, the proxy holding the key, and an "agent" container on the
proxy's internal network running what a hostile test file could run."""

import json
import uuid

import pytest

from cidra.sandbox import limits
from cidra.sandbox.runner import AgentNetwork, _create, _exec_with_timeout, client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M7-KEY-PROXY")

KEY = f"sk-test-{uuid.uuid4().hex}"
# The stand-in endpoint says whether the right key arrived, never the key itself.
ENDPOINT = """
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        body = json.dumps({'key_ok': self.headers.get('x-api-key') == os.environ['EXPECTED']}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
HTTPServer(('0.0.0.0', 9000), H).serve_forever()
"""
# Run as repository code would be, inside the agent's container.
HOSTILE = """
import glob, json, os, socket, urllib.error, urllib.request
out = {'env': dict(os.environ), 'proc': []}
for p in glob.glob('/proc/*/environ') + glob.glob('/proc/*/cmdline'):
    try: out['proc'].append(open(p, 'rb').read().decode('latin-1'))
    except OSError: pass
def reach(host, port):
    try: socket.create_connection((host, port), 3).close(); return True
    except OSError: return False
out['endpoint_direct'] = reach(os.environ['ENDPOINT_IP'], 9000)
out['internet'] = reach('pypi.org', 443)  # the install step reaches it from the normal bridge
def post(path):
    req = urllib.request.Request(os.environ['PROXY'] + path, data=b'{}', method='POST', headers={'x-api-key': 'agent'})
    try: return urllib.request.urlopen(req, timeout=10).read().decode()
    except urllib.error.HTTPError as e: return e.code
out['model_call'] = post('/v1/messages')
out['other_call'] = post('/v1/files')
print(json.dumps(out))
"""


def test_repository_code_cannot_read_the_key_or_go_around_the_proxy():
    endpoint = client().containers.run(limits.IMAGE, ["python", "-c", ENDPOINT], environment={"EXPECTED": KEY},
                                       network_mode="bridge", detach=True)
    try:
        endpoint.reload()
        ip = endpoint.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]
        with AgentNetwork(KEY, f"http://{ip}:9000") as net:
            agent = _create(net.name)
            try:
                agent.start()
                code, out, err = _exec_with_timeout(
                    agent, ["env", f"ENDPOINT_IP={ip}", f"PROXY={net.base_url}", "python", "-c", HOSTILE],
                    60, limits.WORKDIR)
                assert code == 0, err.decode()
                seen = json.loads(out)
            finally:
                agent.remove(force=True)
    finally:
        endpoint.remove(force=True)

    assert KEY not in out.decode()  # not in its environment, any process's, or a reply
    assert json.loads(seen["model_call"]) == {"key_ok": True}  # yet its model call carried the key
    assert seen["other_call"] == 403
    assert not seen["endpoint_direct"] and not seen["internet"]
