"""The measurement harness records every fix attempt and why it did or did not verify."""

from eval.attempts import attempts_from_updates, why_not_verified


def test_three_attempts_that_fail_three_ways():
    updates = [
        ("reproduce_once", {"reproduced": True}),
        ("generate_fix", {"fix_attempts": 1, "fix_diff": "diff-1"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": False, "apply_error": "patch does not apply"}),
        ("verify_fix", {"verified": False}),
        ("generate_fix", {"fix_attempts": 2, "fix_diff": "diff-2"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": True}),
        ("verify_fix", {"verified": False, "regressions": ["tests/b.py::was_green"],
                        "verify_failing_tests": ["tests/b.py::was_green"], "verify_note": "broke"}),
        ("generate_fix", {"fix_attempts": 3, "fix_diff": "diff-3"}),
        ("audit_patch", {"patch_audit_ok": False, "patch_audit_reasons": ["SR-13: ..."]}),
    ]
    attempts = attempts_from_updates(updates)
    assert [a["result"] for a in attempts] == ["did_not_apply", "regression", "refused_by_audit"]
    assert [a["diff"] for a in attempts] == ["diff-1", "diff-2", "diff-3"]
    assert attempts[0]["apply_error"] == "patch does not apply"
    assert attempts[1]["regressions"] == ["tests/b.py::was_green"]


def test_still_failing_empty_and_verified():
    updates = [
        ("generate_fix", {"fix_diff": None}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": False}),
        ("verify_fix", {"verified": False}),
        ("generate_fix", {"fix_diff": "d"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": True}),
        ("verify_fix", {"verified": False, "verify_failing_tests": ["tests/a.py::target"]}),
        ("generate_fix", {"fix_diff": "d2"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": True}),
        ("verify_fix", {"verified": True}),
    ]
    assert [a["result"] for a in attempts_from_updates(updates)] == ["empty_patch", "still_failing", "verified"]


def test_a_cached_fix_and_a_model_error_are_attempts_too():
    updates = [
        ("select_strategy", {"fix_strategy": "patch_source", "cache_hit": True, "fix_diff": "cached"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": True}),
        ("verify_fix", {"verified": False, "verify_note": "the test run after the patch did not complete normally"}),
        ("generate_fix", {"fix_diff": None, "analysis_error": "LLM token cap reached"}),
    ]
    attempts = attempts_from_updates(updates)
    assert [(a["source"], a["result"]) for a in attempts] == [("cache", "did_not_complete"), ("model", "model_error")]


def test_counts_over_runs():
    records = [{"attempts": [{"result": "did_not_apply"}, {"result": "still_failing"}]},
               {"attempts": [{"result": "did_not_apply"}]}, {"attempts": []}]
    assert why_not_verified(records) == {"did_not_apply": 2, "still_failing": 1}


def test_edits_that_could_not_be_placed_count_as_did_not_apply():
    updates = [
        ("generate_fix", {"fix_diff": None, "patch_applied": False, "apply_error": "edit 1: the old text was not found"}),
        ("audit_patch", {"patch_audit_ok": True}),
        ("apply_patch", {"patch_applied": False}),
        ("verify_fix", {"verified": False}),
    ]
    [attempt] = attempts_from_updates(updates)
    assert attempt["result"] == "did_not_apply"
    assert attempt["apply_error"] == "edit 1: the old text was not found"


def test_a_flaky_fixture_gets_more_tries_only_until_detected():
    from eval.attempts import run_flaky_fixture
    outcomes = iter(["failed", "flaky_detected", "failed"])
    seen = []

    def run(fid):
        seen.append(fid)
        return {"outcome": next(outcomes)}

    assert run_flaky_fixture("F-04", run) == {"outcome": "flaky_detected", "tries": 2}
    assert seen == ["F-04", "F-04"]
    never = run_flaky_fixture("F-04", lambda fid: {"outcome": "failed"})
    assert never == {"outcome": "failed", "tries": 3}
