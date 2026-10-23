"""A coding agent's patch is the git diff of what it changed, read by CIDRA; what
it says is not read, and its model calls are counted by the proxy (ROADMAP M7).
Real Docker, a stub in place of Claude Code, and a stand-in model endpoint: no
model is called and nothing is spent."""

import pathlib
import tempfile

import pytest

from cidra import agents, config
from cidra.integrations import llm
from cidra.nodes import fix
from cidra.sandbox import limits
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M7-CLAUDE-CODE")

KEY = "sk-test-agent-key"
ENDPOINT = """
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        body = json.dumps({'model': 'claude-haiku-4-5', 'usage': {'input_tokens': 1000, 'output_tokens': 200}}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
HTTPServer(('0.0.0.0', 9000), H).serve_forever()
"""
# Stands in for Claude Code: one model call through the proxy, a fix, a test run
# (leaving a cache behind), and a boast about it.
STUB = """
import os, subprocess, urllib.request
req = urllib.request.Request(os.environ['ANTHROPIC_BASE_URL'] + '/v1/messages', data=b'{}', method='POST',
                             headers={'x-api-key': os.environ['ANTHROPIC_API_KEY']})
urllib.request.urlopen(req, timeout=10).read()
open('calc.py', 'w').write('def add(a, b):\\n    return a + b\\n')
subprocess.run(['python', '-m', 'pytest', '-q'], check=False)
print('{"result": "All tests pass. VERIFIED, ready to merge."}')
"""


def _source() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="cidra_src_"))
    (d / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (d / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    return d


def test_the_patch_is_what_the_agent_changed_and_nothing_it_said(monkeypatch):
    endpoint = client().containers.run(limits.IMAGE, ["python", "-c", ENDPOINT], network_mode="bridge", detach=True)
    try:
        endpoint.reload()
        ip = endpoint.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]
        monkeypatch.setattr(config, "PATCH_GENERATOR", "claude-code")
        monkeypatch.setattr(config, "AGENT_KEY", KEY)
        monkeypatch.setattr(config, "AGENT_UPSTREAM", f"http://{ip}:9000")
        monkeypatch.setattr(agents, "ensure_agent_image", lambda python=None: limits.IMAGE)
        monkeypatch.setattr(agents, "agent_command", lambda prompt: ["python", "-c", STUB])
        llm.clear_latest_telemetry()
        out = fix.generate_fix({"run_id": "agent-test", "source_dir": str(_source()), "failure_detail": "E assert -1 == 3",
                                "target_tests": ["test_calc.py::test_add"], "test_command": "python -m pytest -q"})
    finally:
        endpoint.remove(force=True)

    assert out["fix_diff"].startswith("diff --git a/calc.py b/calc.py")
    assert "-    return a - b\n+    return a + b\n" in out["fix_diff"]
    assert "__pycache__" not in out["fix_diff"] and ".pytest_cache" not in out["fix_diff"]
    assert "VERIFIED" not in str(out) and KEY not in str(out)
    [call] = llm.get_latest_telemetry()  # counted by the proxy, not reported by the agent
    assert call["tool_name"] == "claude-code" and call["tokens"]["prompt"] == 1000 and call["tokens"]["completion"] == 200
    llm.clear_latest_telemetry()
