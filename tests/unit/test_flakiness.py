"""Phase 8.1 — Deterministic Flakiness Score + isolation (0 repair attempts)."""

from cidra.nodes.reproduce import flakiness_score, classify_flakiness
from cidra.state import SandboxResult
from cidra import routers


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


# --- a runner that never ran is not a reproduced failure ---

def _code(code, out=""):
    return SandboxResult(step="test", exit_code=code, stdout_tail=out,
                         stderr_tail="", duration_s=0.1, timed_out=False)


class _FakeSession:
    def __init__(self, result):
        self.result = result

    def run(self, step, command, timeout_s=None):
        return self.result


def _reproduce(monkeypatch, result):
    from cidra.nodes import reproduce
    monkeypatch.setattr(reproduce, "session_for", lambda run_id: _FakeSession(result))
    return reproduce.reproduce_once({"run_id": "r1"})


def test_missing_pytest_is_not_a_reproduction(monkeypatch):
    out = _reproduce(monkeypatch, _code(127, "sh: 1: pytest: not found"))
    assert out["reproduced"] is False
    assert "127" in out["analysis_error"] and "not found" in out["analysis_error"]


def test_no_tests_collected_is_not_a_reproduction(monkeypatch):
    assert _reproduce(monkeypatch, _code(5))["reproduced"] is False


def test_failed_tests_and_collection_errors_are_reproductions(monkeypatch):
    assert _reproduce(monkeypatch, _code(1))["reproduced"] is True
    assert _reproduce(monkeypatch, _code(2))["reproduced"] is True  # e.g. missing import


def test_flaky_runs_with_missing_runner_are_not_reproduced():
    out = classify_flakiness({"repro_results": [_code(127)] * 5})
    assert out["reproduced"] is False and "analysis_error" in out


# --- the flaky path must be reachable even though policy refuses to patch flaky tests ---

def test_refused_flaky_category_still_takes_the_detection_path():
    from cidra.state import Analysis
    flaky = Analysis(category="flaky_test", confidence=0.8, evidence="e", proposed_action="p")
    state = {"analysis": flaky, "policy_decision": "strict_refusal"}
    assert routers.route_after_validate(state) == "checkout_commit"
    assert routers.route_category(state) == "reproduce_n_times"


def test_other_refused_categories_still_stop_at_the_report():
    from cidra.state import Analysis
    other = Analysis(category="unknown", confidence=0.8, evidence="e", proposed_action="p")
    state = {"analysis": other, "policy_decision": "strict_refusal"}
    assert routers.route_after_validate(state) == "compose_report"


def test_validate_does_not_preset_an_outcome_for_flaky():
    from cidra.nodes.analyze import validate_analysis
    from cidra.state import Analysis
    flaky = Analysis(category="flaky_test", confidence=0.8, evidence="e", proposed_action="p")
    out = validate_analysis({"analysis": flaky})
    assert out["policy_decision"] == "strict_refusal"   # still never patched
    assert "outcome" not in out                          # detection decides the outcome
