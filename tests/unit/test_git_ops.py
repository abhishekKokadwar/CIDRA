"""Phase 9.1 — hardened git wrapper (SR-16). Uses real git on a temp repo."""

import subprocess

import pytest

from cidra import git_ops
from cidra.git_ops import git, hardened_flags


def test_hardened_flags_are_all_present():
    flags = " ".join(hardened_flags())
    assert "protocol.file.allow=never" in flags
    assert "core.hooksPath=/dev/null" in flags
    assert "credential.helper=" in flags


def test_git_call_injects_flags_and_env(monkeypatch):
    seen = {}

    def fake_run(cmd, cwd, env, capture_output, text, timeout, check):
        seen["cmd"] = cmd
        seen["env"] = env
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    git("status")
    # every hardened -c flag is on the command line
    assert "protocol.file.allow=never" in seen["cmd"]
    assert "core.hooksPath=/dev/null" in seen["cmd"]
    assert "credential.helper=" in seen["cmd"]
    # env neutralises system/global config
    assert seen["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert seen["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_command_is_argv_not_shell(monkeypatch):
    """SR-03: git args are a list; no shell string is ever built."""
    captured = {}
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: captured.setdefault("cmd", cmd) or _ok())
    git("log", "--oneline")
    assert isinstance(captured["cmd"], list)  # argv, not a string


def _ok():
    class R: returncode = 0; stdout = ""; stderr = ""
    return R()


# --- functional: real git on a real temp repo ---

@pytest.fixture
def repo(tmp_path):
    git("init", "-q", cwd=tmp_path)
    git("config", "user.email", "t@t", cwd=tmp_path)
    git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    git("add", "-A", cwd=tmp_path)
    git("commit", "-qm", "init", cwd=tmp_path)
    return tmp_path


def test_functional_roundtrip(repo):
    r = git("rev-parse", "HEAD", cwd=repo)
    assert len(r.stdout.strip()) == 40  # a real SHA


def test_check_raises_on_failure(repo):
    with pytest.raises(subprocess.CalledProcessError):
        git("checkout", "no-such-branch", cwd=repo)


def test_hooks_are_disabled(repo, tmp_path):
    """A post-commit hook must NOT run under the wrapper (core.hooksPath=/dev/null)."""
    hooks = repo / ".git" / "hooks"
    canary = tmp_path / "hook_fired"
    (hooks / "post-commit").write_text(f"#!/bin/sh\ntouch '{canary}'\n")
    (hooks / "post-commit").chmod(0o755)
    (repo / "b.txt").write_text("x")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "second", cwd=repo)
    assert not canary.exists()  # hook was suppressed
