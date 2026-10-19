"""A run that crashes mid-graph still removes its container and checkout
(KNOWN_GAPS G-23). `cleanup` is the graph's last node, so an exception in an
earlier one used to skip it and leave the container running.

Needs Docker and the sandbox image (CI builds both).
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import docker
import pytest

from cidra import cli, config
from cidra.state import Analysis
from cidra.nodes import environment
from cidra.sandbox.runner import client

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)


@pytest.mark.req("G-23")
def test_a_crash_after_the_sandbox_started_leaves_no_container_or_checkout(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_calc.py").write_text("def test_add():\n    assert 1 + 1 == 3\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))

    seen = {}

    def crash(state):  # the 2026-10-16 failure: Docker gave out during install
        seen["container"] = environment.session_for(state["run_id"]).container.id
        seen["checkout"] = state["source_dir"]
        raise RuntimeError("Docker went away")

    monkeypatch.setattr(environment, "install_deps", crash)
    analysis = Analysis(category="assertion_error", confidence=0.9, evidence="assert 2 == 3", proposed_action="fix it")
    with patch("cidra.nodes.analyze.analyze_region", return_value=analysis), pytest.raises(SystemExit):
        cli._run_graph({"run_id": "it-crash", "repo": "local/dev", "commit_sha": "HEAD", "dry_run": True,
                        "source_dir": str(repo), "raw_log": "FAILED test_calc.py::test_add - assert 2 == 3"})

    assert seen, "the run crashed before the sandbox started: this test proves nothing"
    with pytest.raises(docker.errors.NotFound):
        client().containers.get(seen["container"])
    assert not Path(seen["checkout"]).exists()
    assert environment.session_for("it-crash") is None
