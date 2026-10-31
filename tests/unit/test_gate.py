"""The gate as one entry point (ROADMAP M8): a commit, the failing tests and a diff
in, a verdict and its evidence out, with no model. No Docker here: a refusal is
decided before the sandbox. tests/integration/test_verify_cli.py runs the rest."""

import subprocess

import pytest

from cidra import config, gate
from cidra.nodes import environment

pytestmark = pytest.mark.req("M8-GATE")

CHEAT = ("--- a/test_calc.py\n+++ b/test_calc.py\n@@ -2,4 +2,4 @@\n \n \n def test_add():\n"
         "-    assert add(1, 2) == 3\n+    pass\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "worktrees"))
    path = tmp_path / "repo"
    path.mkdir()
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (path / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    return path


def test_a_refused_diff_is_a_verdict_with_its_reasons_and_never_runs(repo, monkeypatch):
    monkeypatch.setattr(environment, "prepare_sandbox", lambda state: pytest.fail("a refused diff must not run"))
    verdict = gate.check(str(repo), "HEAD", CHEAT, ["test_calc.py::test_add"])
    assert verdict.outcome == gate.REFUSED and not verdict.verified
    text = verdict.markdown()
    assert text.startswith("⛔ **Refused by CIDRA's audit gate**")
    assert "test_calc.py" in text and verdict.reason in text.replace("\n- ", "; ")


def test_a_check_that_could_not_run_says_so_and_claims_nothing(repo, monkeypatch):
    monkeypatch.setattr(environment, "prepare_sandbox", lambda state: {"env_ready": False, "analysis_error": "no Docker"})
    honest = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
    verdict = gate.check(str(repo), "HEAD", honest, ["test_calc.py::test_add"])
    assert verdict.outcome == gate.ERROR and not verdict.verified
    text = verdict.markdown()
    assert "Could not set up the sandbox: no Docker" in text and "Verified by CIDRA" not in text


@pytest.mark.parametrize("outcome", [gate.VERIFIED, gate.REFUSED, gate.NOT_VERIFIED, gate.NOT_REPRODUCED, gate.ERROR])
def test_every_outcome_has_a_headline_and_only_verified_claims_success(outcome):
    text = gate.Verdict(outcome, "why").markdown()
    assert ("Verified by CIDRA" in text) == (outcome == gate.VERIFIED)
    if outcome not in (gate.VERIFIED, gate.REFUSED):
        assert "why" in text
