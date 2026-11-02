"""A developer's .env that turns agent mode on (for the M7 pilot) changes neither
the test suite nor a stub measurement: both stay on the built-in loop, so neither
starts a real agent on a personal subscription."""

import os
import pathlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.req("M7-GENERATOR")

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _with_agent_env(tmp_path) -> dict:
    env_file = tmp_path / "agent.env"
    env_file.write_text("CIDRA_PATCH_GENERATOR=claude-code\n")
    env = {k: v for k, v in os.environ.items() if k != "CIDRA_PATCH_GENERATOR"}
    return {**env, "CIDRA_ENV_FILE": str(env_file)}


def test_the_suite_ignores_an_agent_set_in_dot_env(tmp_path):
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "tests/unit/test_patch_generator.py::test_the_builtin_loop_is_the_default"],
                         cwd=ROOT, env=_with_agent_env(tmp_path), capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-1500:]


def test_a_stub_measurement_ignores_an_agent_set_in_dot_env(tmp_path):
    probe = ("import sys; sys.argv = ['measure.py', '--stub']; import eval.measure; "
             "from cidra import config; print(config.PATCH_GENERATOR)")
    run = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, env=_with_agent_env(tmp_path),
                         capture_output=True, text=True)
    assert run.stdout.strip().splitlines()[-1:] == ["builtin"], run.stderr[-1500:]
