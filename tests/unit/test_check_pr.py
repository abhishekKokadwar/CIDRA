"""`cidra check-pr` and the Action's check-pr mode (ROADMAP M8): the pull request's
base is the failing commit and its diff is the fix. No Docker here: the gate is
replaced by a recorder; tests/integration/test_check_pr_sandbox.py runs it for real."""

import argparse
import json
import pathlib
import subprocess

import pytest
import yaml

from cidra import cli, gate

pytestmark = pytest.mark.req("M8-CHECK-PR")

ROOT = pathlib.Path(__file__).parents[2]
GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()

    def commit(text, message):
        (path / "calc.py").write_text(text)
        subprocess.run([*GIT, "add", "-A"], cwd=path, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", message], cwd=path, check=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True).stdout.strip()

    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    base = commit("def add(a, b):\n    return a - b\n", "failing")
    head = commit("def add(a, b):\n    return a + b\n", "fix")
    return path, base, head


@pytest.fixture
def seen(monkeypatch, tmp_path):
    calls = []

    def fake_check(source, sha, diff, targets, install=None, test=None):
        calls.append({"sha": sha, "diff": diff, "targets": targets})
        return gate.Verdict(gate.REFUSED, "r", {"patch_audit_reasons": ["it weakens a test"]})
    monkeypatch.setattr(gate, "check", fake_check)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output.txt"))
    monkeypatch.delenv("CIDRA_SOURCE_DIR", raising=False)
    return calls


def _args(**kw):
    return argparse.Namespace(**{"base": None, "head": None, "source": None, "target": None, "out": None, **kw})


def test_the_pull_requests_base_and_diff_come_from_the_event(repo, seen, monkeypatch, tmp_path):
    path, base, head = repo
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    out = tmp_path / "verdict.md"
    assert cli.check_pr_run(_args(source=str(path), out=str(out))) == 1
    [call] = seen
    assert call["sha"] == base and "-    return a - b\n+    return a + b\n" in call["diff"] and call["targets"] == []
    for written in (out, tmp_path / "summary.md"):
        assert "Refused by CIDRA's audit gate" in written.read_text(encoding="utf-8")
        assert "it weakens a test" in written.read_text(encoding="utf-8")
    assert (tmp_path / "output.txt").read_text() == "verdict=refused\n"


def test_a_pull_request_that_changes_nothing_is_not_verified_without_running(repo, seen, tmp_path):
    path, base, _ = repo
    assert cli.check_pr_run(_args(source=str(path), base=base, head=base)) == 1
    assert seen == [] and (tmp_path / "output.txt").read_text() == "verdict=not_verified\n"


def test_outside_a_pull_request_it_says_what_it_needs(seen, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert cli.check_pr_run(_args()) == 1
    assert "pull_request event" in capsys.readouterr().out and seen == []


def test_the_action_runs_the_check_without_a_token_and_comments_without_pr_code():
    steps = {s["name"]: s for s in yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["runs"]["steps"]}
    check, comment = steps["Check the pull request"], steps["Comment on the pull request"]
    assert "cidra check-pr" in check["run"] and check["if"] == "inputs.mode == 'check-pr'"
    assert not [k for k in check.get("env", {}) if "TOKEN" in k or "KEY" in k]  # nothing to steal
    assert "cidra" not in comment["run"].replace("cidra-verdict", "") and "pip" not in comment["run"]
    assert comment["if"].startswith("always()")  # a refusal fails the check step; it is still posted
    assert steps["Run CIDRA"]["if"] == "inputs.mode != 'check-pr'"  # fix mode is unchanged
