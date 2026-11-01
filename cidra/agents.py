"""Coding agents as patch generators (ROADMAP M7).

The agent edits a copy of the checkout in its own container, on a network that
reaches only the model-key proxy (sandbox.runner.AgentNetwork). CIDRA then reads
the change with git: that diff is the agent's whole contribution. What the agent
says about it (tests run, "fixed") is never read; the gate decides.
"""

import logging
from pathlib import Path

from docker.errors import DockerException, NotFound

from cidra import config
from cidra.integrations.llm import record_usage
from cidra.nodes.environment import env_prefix, session_for
from cidra.sandbox import limits
from cidra.sandbox.runner import AgentNetwork, _create, _exec_with_timeout, _tail, _tar_bytes, ensure_agent_image
from cidra.state import DebugState

log = logging.getLogger(__name__)

PROMPT = """A CI run failed on this repository. Fix the code under test so the failing tests pass.

Rules:
- Change the code under test, not the tests. Never weaken, skip or delete a test or its setup.
- Make the smallest change that fixes the cause. No refactors, no unrelated edits.
- Do not silence the error: no deleting a raise, no except clause that ignores it.
- Do not commit. Leave your changes in the working tree.

You can run the tests with: {test_command}

Failing tests:
{targets}

{detail}"""

# Never part of the diff: files a test run leaves behind.
_NOT_CHANGES = ["--", ".", ":!**/__pycache__/**", ":!.pytest_cache/**", ":!**/*.pyc"]
_GIT = ["git", "-c", "user.name=cidra", "-c", "user.email=cidra@localhost"]


def prompt_for(state: DebugState) -> str:
    targets = "\n".join(state.get("target_tests") or []) or "(named in the output below)"
    detail = state.get("failure_detail") or state.get("error_region") or ""
    test_command = env_prefix(state) + (state.get("test_command") or config.TEST_COMMAND)
    text = PROMPT.format(test_command=test_command, targets=targets, detail=detail[-8000:])
    if note := state.get("verify_note"):
        text += f"\n\nA previous attempt did not work: {note[:1500]}"
    return text


def agent_command(prompt: str) -> list[str]:
    """Claude Code, headless. --bare skips the machine's hooks, plugins and
    CLAUDE.md, so every run sees the same agent. Permissions are not asked: the
    container is the boundary, and the gate judges the result. An argument list,
    never a shell string (SR-03)."""
    cmd = ["claude", "-p", prompt, "--bare", "--permission-mode", "bypassPermissions",
           "--no-session-persistence", "--output-format", "json", "--max-budget-usd", str(config.AGENT_MAX_USD)]
    return cmd + (["--model", config.AGENT_MODEL] if config.AGENT_MODEL else [])


def _copy_packages(session, box) -> None:
    """The run's installed dependencies, so the agent can run the tests: its
    network cannot install them."""
    try:
        blob = b"".join(session._box.get_archive(limits.SITE)[0])
    except NotFound:
        return
    box.put_archive(str(Path(limits.SITE).parent.as_posix()), blob)


def claude_code_patch(state: DebugState) -> dict:
    key = config.AGENT_KEY or config.API_KEY  # at call time, like the other settings
    if not key:
        return {"fix_diff": None, "analysis_error": "the coding agent has no key: set CIDRA_AGENT_KEY"}
    try:
        image = ensure_agent_image(state.get("python_version"))
        with AgentNetwork(key, config.AGENT_UPSTREAM, config.AGENT_AUTH, config.AGENT_MAX_REQUESTS) as net:
            box = _create(net.name, image, extra_env={
                "ANTHROPIC_BASE_URL": net.base_url,
                "ANTHROPIC_API_KEY": "held-by-the-cidra-proxy",  # the proxy puts the real one on
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            })
            try:
                box.start()
                box.put_archive(limits.WORKDIR, _tar_bytes(Path(state.get("source_dir") or config.PRACTICE_REPO_DIR)))
                if (session := session_for(state["run_id"])) is not None:
                    _copy_packages(session, box)
                base = _exec_with_timeout(box, [*_GIT, "init", "-q"], 60, limits.WORKDIR)[0] == 0 and \
                    _exec_with_timeout(box, ["sh", "-c", " ".join(_GIT) + " add -A && " + " ".join(_GIT)
                                             + " commit -qm before-the-agent"], 300, limits.WORKDIR)[0] == 0
                if not base:
                    return {"fix_diff": None, "analysis_error": "could not record the checkout before the agent ran"}
                code, out, err = _exec_with_timeout(box, agent_command(prompt_for(state)), config.AGENT_TIMEOUT,
                                                    limits.WORKDIR)
                _exec_with_timeout(box, [*_GIT, "add", "-A"], 120, limits.WORKDIR)
                diff_code, diff, diff_err = _exec_with_timeout(
                    box, [*_GIT, "diff", "--cached", "--no-color", "HEAD", *_NOT_CHANGES], 120, limits.WORKDIR)
            finally:
                box.remove(force=True)
            for usage in net.usage():
                record_usage(usage, tool_name="claude-code")
    except (DockerException, RuntimeError) as e:
        return {"fix_diff": None, "analysis_error": f"the coding agent did not run: {e}"[:500]}
    if diff_code != 0:
        return {"fix_diff": None, "analysis_error": f"could not read the agent's changes: {_tail(diff_err)[-300:]}"}
    if not diff.strip():
        why = "timed out" if code is None else f"exited {code}"
        # What the agent says ("fixed, all tests pass") is not evidence, so the
        # report never quotes it: the operator's log keeps it for debugging.
        log.info("the coding agent changed nothing (%s): %s", why, _tail(err or out)[-300:])
        return {"fix_diff": None, "analysis_error": f"the coding agent changed nothing ({why})"}
    return {"fix_diff": diff.decode("utf-8", "replace")}
