"""Tier 1 checks: pure logic only, no network, no Docker. See docs/5_fixtures.md §6."""

from cidra import routers
from cidra.graph import build_graph
from cidra.nodes.ingest import isolate_error
from cidra.nodes.reproduce import classify_flakiness
from cidra.state import Analysis, SandboxResult

LOG = "\n".join(
    [f"2026-08-21T10:00:0{i}Z setup line {i}" for i in range(10)]
    + ["2026-08-21T10:00:10Z \x1b[31mModuleNotFoundError: No module named 'requests'\x1b[0m"]
    + [f"2026-08-21T10:00:1{i}Z after {i}" for i in range(1, 5)]
)


def test_isolate_strips_noise_and_finds_marker():
    out = isolate_error({"raw_log": LOG})
    assert "ModuleNotFoundError" in out["error_region"]
    assert "\x1b[" not in out["error_region"]
    assert "2026-08-21T" not in out["error_region"]
    assert out["log_markers"] == ["ModuleNotFoundError"]


def test_isolate_no_marker_falls_back_to_tail():
    out = isolate_error({"raw_log": "all\nquiet\nhere"})
    assert out["log_markers"] == []
    assert "here" in out["error_region"]


def test_isolate_marks_gaps():
    # Two hits far apart must not read as one contiguous region.
    log = "\n".join(["AssertionError"] + ["pad"] * 300 + ["KeyError"])
    assert "..." in isolate_error({"raw_log": log})["error_region"]


def _res(code):
    return SandboxResult(
        step="test", exit_code=code, stdout_tail="", stderr_tail="", duration_s=0.1, timed_out=False
    )


def test_flaky_mixed_results_is_flaky():
    out = classify_flakiness({"repro_results": [_res(0), _res(1), _res(0), _res(1), _res(1)]})
    assert out["outcome"] == "flaky_detected"
    assert out["flaky_pass_count"] == 2


def test_flaky_all_pass_is_not_reproduced():
    out = classify_flakiness({"repro_results": [_res(0)] * 5})
    assert out["reproduced"] is False
    assert "outcome" not in out


def test_flaky_all_fail_is_deterministic():
    out = classify_flakiness({"repro_results": [_res(1)] * 5})
    assert out["reproduced"] is True


def test_install_result_does_not_count_as_a_flaky_pass():
    # install_deps appends to the same repro_results list. Counting its pass
    # would make a deterministic failure look mixed, i.e. falsely flaky.
    install = SandboxResult(
        step="install", exit_code=0, stdout_tail="", stderr_tail="", duration_s=1.0, timed_out=False
    )
    out = classify_flakiness({"repro_results": [install] + [_res(1)] * 5})
    assert out.get("outcome") != "flaky_detected", "install pass leaked into the flaky count"
    assert out["reproduced"] is True


def test_timed_out_never_passes():
    r = SandboxResult(
        step="test", exit_code=0, stdout_tail="", stderr_tail="", duration_s=9.9, timed_out=True
    )
    assert not r.passed


def test_analysis_retries_then_gives_up():
    assert routers.route_after_validate({"analysis_attempts": 1}) == "analyze"
    assert routers.route_after_validate({"analysis_attempts": 2}) == "compose_report"


def test_flaky_category_takes_the_n_times_path():
    a = Analysis(category="flaky_test", confidence=0.9, evidence="e", proposed_action="p")
    assert routers.route_category({"analysis": a}) == "reproduce_n_times"
    assert routers.route_category({}) == "reproduce_once"


def test_no_strategy_skips_the_fix_loop():
    # An unknown category has no repair path; entering the loop would spend
    # MAX_FIX_ATTEMPTS LLM calls to reach the same diagnosis_only outcome.
    assert routers.route_after_strategy({"fix_strategy": None}) == "compose_report"
    assert routers.route_after_strategy({}) == "compose_report"
    assert routers.route_after_strategy({"fix_strategy": "append_requirement"}) == "generate_fix"


def test_env_config_has_no_fix_strategy():
    # The fix would edit .github/workflows/ci.yml, but the sandbox runs pytest
    # directly and never reads it, so verify_fix could not confirm the patch.
    # Diagnosis-only is the honest outcome. See docs/4_architecture.md 5.1.
    from cidra.nodes.fix import STRATEGIES, select_strategy

    assert "env_config_error" not in STRATEGIES
    a = Analysis(category="env_config_error", confidence=0.9, evidence="e", proposed_action="p")
    assert select_strategy({"analysis": a}) == {"fix_strategy": None}
    assert routers.route_after_strategy({"fix_strategy": None}) == "compose_report"


def test_fix_loop_is_bounded():
    assert routers.route_after_verify({"verified": False, "fix_attempts": 2}) == "generate_fix"
    assert routers.route_after_verify({"verified": False, "fix_attempts": 3}) == "compose_report"
    assert routers.route_after_verify({"verified": True, "fix_attempts": 0}) == "compose_report"


def test_audit_gate_blocks_unsafe_patch_from_sandbox():
    # A rejected patch (Phase 10) must route to the report, never to apply_patch.
    assert routers.route_after_audit({"patch_audit_ok": False}) == "compose_report"
    assert routers.route_after_audit({"patch_audit_ok": True}) == "apply_patch"
    assert routers.route_after_audit({}) == "compose_report"  # fail safe


def test_graph_compiles_and_terminates(monkeypatch):
    # No model in a unit test: a failing analyze must still end the graph cleanly.
    def no_llm(_region):
        raise RuntimeError("no LLM in unit tests")
    monkeypatch.setattr("cidra.nodes.analyze.analyze_region", no_llm)
    g = build_graph()
    final = g.invoke({"run_id": "t1", "repo": "x/y", "commit_sha": "abc", "raw_log": LOG})
    assert "error_region" in final


if __name__ == "__main__":
    import sys

    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    sys.exit(0)
