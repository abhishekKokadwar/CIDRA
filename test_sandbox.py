"""Sandbox safety checks. See docs/6_sandbox_spec.md §8 (ADV-01..ADV-08).

Needs Docker. These assert the isolation properties hold, not just that commands run.
Run: python test_sandbox.py
"""

import pathlib
import tempfile

from cidra.sandbox import limits
from cidra.sandbox.runner import client, run_in_sandbox

REPO = pathlib.Path("d:/CODES/cidra-practice")


def _tmp_source() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="cidra_src_"))
    (d / "hello.py").write_text("print('hi')\n")
    return d


def test_runs_a_command():
    r = run_in_sandbox("test", _tmp_source(), "python hello.py")
    assert r.exit_code == 0, r.stderr_tail
    assert "hi" in r.stdout_tail
    assert r.passed


def test_red_test_is_a_result_not_an_exception():
    r = run_in_sandbox("test", _tmp_source(), "exit 3")
    assert r.exit_code == 3
    assert not r.passed


def test_runs_as_non_root():
    r = run_in_sandbox("test", _tmp_source(), "id -un && id -u")
    assert limits.USER in r.stdout_tail
    assert "\n0\n" not in r.stdout_tail, "running as uid 0"


def test_network_is_off_for_test_step():
    # ADV-03: exfiltration attempt from the step where LLM patches execute.
    r = run_in_sandbox(
        "test", _tmp_source(), "python -c \"import socket;socket.create_connection(('1.1.1.1',53),3)\""
    )
    assert r.exit_code != 0, "network reachable during test step"


def test_network_is_on_only_for_install():
    r = run_in_sandbox("install", _tmp_source(), "python -c \"import socket;socket.gethostbyname('pypi.org')\"")
    assert r.exit_code == 0, f"install has no network: {r.stderr_tail}"


def test_timeout_kills_and_reports():
    # ADV-05: infinite loop.
    r = run_in_sandbox("test", _tmp_source(), "sleep 30", timeout_s=5)
    assert r.timed_out
    assert not r.passed
    assert r.duration_s < 25


def test_docker_socket_absent():
    # ADV-01: the container must not be able to reach the daemon.
    r = run_in_sandbox("test", _tmp_source(), "test -S /var/run/docker.sock && echo PRESENT || echo ABSENT")
    assert "ABSENT" in r.stdout_tail


def test_no_host_secrets_in_env():
    # ADV-07: the API key must never be visible inside the container.
    r = run_in_sandbox("test", _tmp_source(), "env")
    for leaked in ("CIDRA_API_KEY", "ANTHROPIC", "GITHUB_TOKEN", "sk-or-v1"):
        assert leaked not in r.stdout_tail, f"{leaked} leaked into the container"


def test_pids_limit_blocks_fork_bomb():
    # ADV-04: the limit must stop it, and the call must return rather than hang.
    r = run_in_sandbox(
        "test",
        _tmp_source(),
        'python -c "import os\nfor _ in range(500): os.fork()" 2>&1 | tail -2',
        timeout_s=30,
    )
    assert not r.timed_out, "fork bomb was not bounded by pids_limit"
    assert "Resource temporarily unavailable" in r.stdout_tail, r.stdout_tail[-200:]


def test_patch_is_applied_as_data():
    src = _tmp_source()
    (src / "hello.py").write_text("print('old')\n")
    diff = (
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )
    r = run_in_sandbox("test", src, "python hello.py", patch=diff)
    assert r.exit_code == 0, r.stderr_tail
    assert "new" in r.stdout_tail


def test_bad_patch_fails_cleanly():
    src = _tmp_source()
    bad = "--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n"
    r = run_in_sandbox("test", src, "echo SHOULD_NOT_RUN", patch=bad)
    assert not r.passed
    assert "SHOULD_NOT_RUN" not in r.stdout_tail, "command ran despite failed patch"


def test_session_survives_install_across_steps():
    # The gap run_in_sandbox alone cannot cover: pip must outlive the install step.
    from cidra.sandbox.runner import Session

    with Session(_tmp_source()) as s:
        assert s.install("pip install --quiet six").passed
        r = s.run("test", "python -c 'import six; print(six.__name__)'")
    assert "six" in r.stdout_tail, r.stderr_tail


def test_session_has_no_network():
    from cidra.sandbox.runner import Session

    with Session(_tmp_source()) as s:
        r = s.run("test", "python -c \"import socket;socket.create_connection(('1.1.1.1',53),3)\"")
    assert r.exit_code != 0, "session container reached the network"


def test_session_install_step_is_rejected():
    from cidra.sandbox.runner import Session

    with Session(_tmp_source()) as s:
        try:
            s.run("install", "true")
        except ValueError:
            return
    raise AssertionError("run() accepted an install step")


def test_container_is_removed():
    before = {c.id for c in client().containers.list(all=True)}
    run_in_sandbox("test", _tmp_source(), "true")
    after = {c.id for c in client().containers.list(all=True)}
    assert after == before, "container leaked"




if __name__ == "__main__":
    import traceback

    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            failed += 1
            print("FAIL", name, "-", e)
        except Exception:
            failed += 1
            print("ERR ", name)
            traceback.print_exc()
    print(f"\n{failed} failed")
    raise SystemExit(1 if failed else 0)
