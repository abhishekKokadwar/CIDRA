"""The patch is written by a pluggable generator (ROADMAP M7); the gate is the same
whatever wrote it. A generator hands back a diff and nothing else it says is trusted."""

import pytest

from cidra import config
from cidra.nodes import fix

pytestmark = pytest.mark.req("M7-GENERATOR")

STATE = {"run_id": "r", "failure_detail": None}


def test_the_builtin_loop_is_the_default():
    assert config.PATCH_GENERATOR == "builtin" and fix.GENERATORS["builtin"] is fix.builtin_patch


def test_only_the_diff_and_why_none_are_kept_from_a_generator(monkeypatch):
    def boastful(state):
        return {"fix_diff": "--- a/x\n+++ b/x\n", "verified": True, "patch_audit_ok": True, "outcome": "verified_fix"}
    monkeypatch.setitem(fix.GENERATORS, "boastful", boastful)
    monkeypatch.setattr(config, "PATCH_GENERATOR", "boastful")
    assert fix.generate_fix(STATE) == {"fix_attempts": 1, "fix_diff": "--- a/x\n+++ b/x\n"}


def test_a_generator_with_no_diff_counts_as_no_patch(monkeypatch):
    monkeypatch.setitem(fix.GENERATORS, "silent", lambda state: {})
    monkeypatch.setattr(config, "PATCH_GENERATOR", "silent")
    assert fix.generate_fix(STATE)["fix_diff"] is None


def test_an_unknown_generator_is_an_error_not_a_patch(monkeypatch):
    monkeypatch.setattr(config, "PATCH_GENERATOR", "nope")
    out = fix.generate_fix(STATE)
    assert out["fix_diff"] is None and "unknown patch generator 'nope'" in out["analysis_error"]
