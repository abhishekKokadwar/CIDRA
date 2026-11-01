"""A personal login used for an agent run stays on the host (ROADMAP M7 pilot).
With a subscription token in the host's environment and ~/.claude, neither the
verification sandbox nor the agent's container can see it: the agent holds only
a placeholder key, and the proxy alone puts the token on its model calls as a
bearer token. Real Docker, a stub agent and a stand-in endpoint; nothing is spent."""

import json
import pathlib
import uuid

import pytest

from cidra import agents, config
from cidra.nodes import fix
from cidra.sandbox import limits, runner
from cidra.sandbox.runner import Session, _exec_with_timeout, client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

pytestmark = pytest.mark.req("M7-KEY-PROXY", "M7-CLAUDE-CODE")

TOKEN = f"sk-ant-oat01-test-{uuid.uuid4().hex}"
# The stand-in endpoint says how the call was authorised, never with what.
ENDPOINT = """
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        body = json.dumps({'bearer_ok': self.headers.get('authorization') == 'Bearer ' + os.environ['EXPECTED'],
                           'x_api_key_sent': 'x-api-key' in self.headers,
                           'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
HTTPServer(('0.0.0.0', 9000), H).serve_forever()
"""
# What any code in a container can see of its environment and home directories.
PROBE = """
import glob, json, os
proc = []
for p in glob.glob('/proc/*/environ') + glob.glob('/proc/*/cmdline'):
    try: proc.append(open(p, 'rb').read().decode('latin-1'))
    except OSError: pass
claude = [d for d in {os.path.expanduser('~'), '/root', *glob.glob('/home/*')} if os.path.exists(d + '/.claude')]
seen = {'env': dict(os.environ), 'proc': proc, 'claude_dirs': claude}
"""
# The agent's report can only leave its container as a file in the diff.
AGENT = PROBE + """
import urllib.request
req = urllib.request.Request(os.environ['ANTHROPIC_BASE_URL'] + '/v1/messages', data=b'{}', method='POST',
                             headers={'x-api-key': os.environ['ANTHROPIC_API_KEY']})
seen['reply'] = json.loads(urllib.request.urlopen(req, timeout=10).read())
open('seen.json', 'w').write(json.dumps(seen) + '\\n')
"""


@pytest.fixture
def logged_in(tmp_path, monkeypatch):
    """The host as the pilot leaves it: the token in the environment and in ~/.claude."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text(json.dumps({"accessToken": TOKEN}))
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("CIDRA_AGENT_KEY", TOKEN)
    src = tmp_path / "src"
    src.mkdir()
    (src / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    return src


def _clean(attrs: dict) -> None:
    assert attrs["Mounts"] == [] and not attrs["HostConfig"].get("Binds")
    assert not any(TOKEN in e or e.startswith("CLAUDE_CODE_OAUTH_TOKEN=") for e in attrs["Config"]["Env"])


def test_the_verification_sandbox_cannot_see_the_login(logged_in):
    with Session(logged_in) as session:
        box = session._box
        box.reload()
        _clean(box.attrs)
        code, out, err = _exec_with_timeout(box, ["python", "-c", PROBE + "print(json.dumps(seen))"],
                                            60, limits.WORKDIR)
    assert code == 0, err.decode()
    assert TOKEN not in out.decode() and json.loads(out)["claude_dirs"] == []


def test_the_agent_holds_a_placeholder_and_the_proxy_sends_the_token_as_bearer(logged_in, monkeypatch):
    endpoint = client().containers.run(limits.IMAGE, ["python", "-c", ENDPOINT], environment={"EXPECTED": TOKEN},
                                       network_mode="bridge", detach=True)
    created = []

    def create(*args, **kwargs):
        box = runner._create(*args, **kwargs)
        box.reload()
        created.append(box.attrs)
        return box
    try:
        endpoint.reload()
        ip = endpoint.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]
        monkeypatch.setattr(config, "PATCH_GENERATOR", "claude-code")
        monkeypatch.setattr(config, "AGENT_KEY", TOKEN)
        monkeypatch.setattr(config, "AGENT_AUTH", "bearer")
        monkeypatch.setattr(config, "AGENT_UPSTREAM", f"http://{ip}:9000")
        monkeypatch.setattr(agents, "ensure_agent_image", lambda python=None: limits.IMAGE)
        monkeypatch.setattr(agents, "agent_command", lambda prompt: ["python", "-c", AGENT])
        monkeypatch.setattr(agents, "_create", create)
        out = fix.generate_fix({"run_id": "pilot-isolation", "source_dir": str(logged_in),
                                "failure_detail": "E assert -1 == 3", "target_tests": ["test_calc.py::test_add"],
                                "test_command": "python -m pytest -q"})
    finally:
        endpoint.remove(force=True)

    [attrs] = created
    _clean(attrs)
    [line] = [ln[1:] for ln in out["fix_diff"].splitlines() if ln.startswith("+{")]
    seen = json.loads(line)
    assert TOKEN not in line and seen["claude_dirs"] == []
    assert seen["env"]["ANTHROPIC_API_KEY"] == "held-by-the-cidra-proxy"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in seen["env"]
    # The subscription, not an API key, paid for the call: bearer on, no x-api-key.
    assert seen["reply"]["bearer_ok"] is True and seen["reply"]["x_api_key_sent"] is False
    assert pathlib.Path(logged_in, "seen.json").exists() is False  # the agent worked on a copy
