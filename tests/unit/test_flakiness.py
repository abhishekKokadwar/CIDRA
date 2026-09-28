"""Phase 8.1 — Deterministic Flakiness Score + isolation (0 repair attempts)."""

from cidra.nodes.reproduce import flakiness_score, classify_flakiness
from cidra.state import SandboxResult


def _res(passed):
    return SandboxResult(step="test", exit_code=0 if passed else 1,
                         stdout_tail="", stderr_tail="", duration_s=0.1, timed_out=False)


# --- score math ---

def test_score_unanimous_pass_is_zero():
    assert flakiness_score(5, 5) == 0


def test_score_unanimous_fail_is_zero():
    assert flakiness_score(0, 5) == 0


def test_score_perfect_split_is_max():
    assert flakiness_score(2, 4) == 100          # 2 pass / 2 fail
    assert flakiness_score(3, 6) == 100


def test_score_monotonic_toward_split():
    # 6 runs: more balanced => higher score
    assert flakiness_score(1, 6) < flakiness_score(2, 6) < flakiness_score(3, 6)


def test_score_one_flip_in_five():
    # 4 pass / 1 fail on 5 runs => |4-1|/5 = 0.6 => 40
    assert flakiness_score(4, 5) == 40


def test_score_empty_is_zero():
    assert flakiness_score(0, 0) == 0


# --- classification / isolation ---

def test_intermittent_is_flaky_with_zero_repair():
    """Exit criterion: intermittent => FLAKY, and the graph never enters the fix path."""
    state = {"repro_results": [_res(True), _res(False), _res(True), _res(False), _res(False)]}
    out = classify_flakiness(state)
    assert out["outcome"] == "flaky_detected"
    assert out["flaky_score"] > 0
    # flaky_detected routes straight to compose_report — no select_strategy/generate_fix.
    from cidra import routers
    assert routers.route_after_flaky({"outcome": "flaky_detected"}) == "compose_report"


def test_all_fail_is_not_flaky_falls_through():
    state = {"repro_results": [_res(False)] * 5}
    out = classify_flakiness(state)
    assert "outcome" not in out and out["reproduced"] is True and out["flaky_score"] == 0


def test_all_pass_is_not_the_failure():
    state = {"repro_results": [_res(True)] * 5}
    out = classify_flakiness(state)
    assert out["reproduced"] is False and out["flaky_score"] == 0
