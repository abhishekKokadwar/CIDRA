"""Hardened git. The ONLY module that shells out to git. Phase 9, step 9.1.

Implements SR-16 / SR-17 (docs/threat/security_requirements.md), which exist
because CIDRA's preferred checkout runs git on the HOST (docs/6_sandbox_spec.md
§5) — so a poisoned .git/config or hook in an attacker's repo would be *host*
RCE, outside every container control. This is the sharpest edge in the design
(attack_taxonomy.md chain 5 / SEC-04).

Every git call goes through `git()` here, and `git()` always sets:
  - GIT_CONFIG_NOSYSTEM=1        ignore /etc/gitconfig
  - GIT_CONFIG_GLOBAL=/dev/null  ignore ~/.gitconfig (aliases, hooks)
  - -c protocol.file.allow=never block file:// submodule/transport tricks
  - -c core.hooksPath=/dev/null  no repo hook ever runs
  - GIT_TERMINAL_PROMPT=0 + empty credential helper — never block on / leak creds

A hook or alias that fires is a containment failure; SEC-04's canary proves it
does not. No other module may call git directly — that is the SR-16 discipline.
"""

import subprocess
from pathlib import Path

# Set on the child env, not the parent — every call is self-contained.
_HARDENED_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}

# -c flags applied to every invocation. Config beats env for these.
_HOOKS_OFF = "core.hooksPath=/dev/null"
_NO_CRED = "credential.helper="
_FILE_NEVER = "protocol.file.allow=never"
_FILE_USER = "protocol.file.allow=user"  # only for an explicit top-level local clone


# Config keys that let a repo-local .git/config execute an arbitrary command when
# an ordinary git operation runs. hooksPath alone is NOT enough: fsmonitor,
# sshCommand, external diff/pager, and the fsmonitor hook all run programs from
# config. A poisoned repo sets these; we override each to empty on every call.
# (SEC-04 caught this — core.fsmonitor fired on `git status` despite hooksPath.)
_NEUTRALIZE = (
    "core.fsmonitor=",
    "core.sshCommand=",
    "core.pager=cat",
    "core.editor=true",
    "diff.external=",
    "sequence.editor=true",
    "uploadpack.packObjectsHook=",
)


def _flags(allow_file: bool) -> list[str]:
    # file transport is 'never' everywhere EXCEPT the one top-level local clone we
    # ourselves initiate. Even then, submodule recursion stays off (see git()), so
    # a malicious .gitmodules can't ride a file:// fetch in on our clone.
    proto = _FILE_USER if allow_file else _FILE_NEVER
    flags = ["-c", proto, "-c", _HOOKS_OFF, "-c", _NO_CRED]
    for kv in _NEUTRALIZE:
        flags += ["-c", kv]
    return flags


def git(*args: str, cwd: str | Path | None = None, timeout: int = 120,
        check: bool = True, allow_file: bool = False) -> subprocess.CompletedProcess:
    """Run one git command under the hardened configuration.

    argv only — never a shell string, so no external value is ever interpolated
    into a command (SR-03). Raises CalledProcessError on non-zero when check.

    `allow_file=True` permits the file transport for THIS call only — used solely
    by the top-level local clone in checkout.py. It never enables submodule
    recursion, so it cannot be leveraged to fetch attacker-chosen file:// repos.
    """
    import os

    env = {**os.environ, **_HARDENED_ENV}
    cmd = ["git", *_flags(allow_file), *args]
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        capture_output=True, text=True, timeout=timeout, check=check,
    )


def hardened_flags() -> list[str]:
    """The -c flags for a normal call, exposed so tests can assert them."""
    return _flags(allow_file=False)
