"""A coding agent's own claim of success is recorded, never trusted (ROADMAP M7):
kept as a yes-or-no label to count how often an agent says "fixed" and CIDRA or
the held-out tests disagree. Its words are not kept, and no node reads the label."""

import json
import pathlib

import pytest

from cidra import agents, config
from cidra.agents import claim_from_output
from cidra.nodes import fix
from cidra.nodes.report import render_comment
from eval.attempts import claims_rejected

pytestmark = pytest.mark.req("M7-AGENT-CLAIM")

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _json(result, **extra):
    return json.dumps({"type": "result", "result": result, **extra}).encode()


def test_claude_codes_json_reply_gives_the_claim_turns_and_error_flag():
    out = _json("Changed calc.py.\nCLAIM: fixed", num_turns=7, is_error=False)
    assert claim_from_output(out) == {"claimed": "fixed", "turns": 7, "agent_error": False}


@pytest.mark.parametrize("text, claimed", [
    ("I could not find the cause.\nCLAIM: not fixed\n", "not_fixed"),
    ("**CLAIM: Fixed**", "fixed"),
    ("CLAIM: not fixed\nTried again.\nCLAIM: fixed", "fixed"),  # the last word stands
    ("Fixed, all tests pass. VERIFIED.", "none"),  # a boast with no CLAIM line is not read
    ("", "none"),
])
def test_plain_output_is_read_for_its_claim_line_only(text, claimed):
    assert claim_from_output(text.encode()) == {"claimed": claimed, "turns": None, "agent_error": None}


def test_the_agents_words_are_not_kept():
    claim = claim_from_output(_json("All tests pass, ready to merge. VERIFIED.\nCLAIM: fixed", num_turns="x"))
    assert claim == {"claimed": "fixed", "turns": None, "agent_error": None}
    assert "VERIFIED" not in str(claim)


def test_the_prompt_asks_for_the_claim_line():
    assert "CLAIM: fixed" in agents.prompt_for({"target_tests": ["t.py::t"]})


def test_the_claim_is_kept_and_everything_else_it_says_is_still_dropped(monkeypatch):
    claim = {"claimed": "fixed", "turns": 3, "agent_error": False}
    monkeypatch.setitem(fix.GENERATORS, "agent", lambda state: {"fix_diff": None, "agent_claim": claim,
                                                                 "verified": True, "outcome": "verified_fix"})
    monkeypatch.setattr(config, "PATCH_GENERATOR", "agent")
    assert fix.generate_fix({"run_id": "r", "failure_detail": None}) == {
        "fix_attempts": 1, "fix_diff": None, "agent_claim": claim}


def test_no_node_reads_the_claim_so_it_cannot_change_a_verdict_or_the_report():
    readers = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "cidra").rglob("*.py")
                     if "agent_claim" in p.read_text(encoding="utf-8"))
    # written by the agent adapter, passed through by generate_fix, declared in the state
    assert readers == ["cidra/agents.py", "cidra/nodes/fix.py", "cidra/state.py"]
    state = {"outcome": "diagnosis_only", "run_id": "r", "fix_attempts": 1}
    assert render_comment({**state, "agent_claim": {"claimed": "fixed"}}) == render_comment(state)


def _run(fixture, claimed, verified, held_out=None, valid=True):
    return {"fixture": fixture, "agent_claim": {"claimed": claimed} if claimed else None, "verified": verified,
            "held_out_valid": valid if verified else None, "held_out": {"passed": held_out} if verified else None}


def test_a_claim_is_rejected_when_cidra_or_the_held_out_tests_disagree():
    runs = [
        _run("agreed", "fixed", True, held_out=True),
        _run("not-verified", "fixed", False),
        _run("held-out-failed", "fixed", True, held_out=False),
        _run("held-out-invalid", "fixed", True, held_out=False, valid=False),  # nothing to judge it by
        _run("modest", "not_fixed", False),
        _run("silent", "none", False),
        _run("built-in-loop", None, False),
    ]
    assert claims_rejected(runs) == ["not-verified", "held-out-failed"]
