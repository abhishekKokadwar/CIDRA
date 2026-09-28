"""Phase 6.1 — comment body composition. Pure, no network."""

from cidra.nodes.report import render_comment, _MARKER, MAX_PROSE, MAX_DIFF
from cidra.state import Analysis


def _analysis(**kw):
    base = dict(category="missing_dependency", confidence=0.9,
                evidence="No module named 'requests'", proposed_action="add requests")
    base.update(kw)
    return Analysis(**base)


def test_verified_fix_shows_diff():
    body = render_comment({
        "outcome": "verified_fix", "verified": True,
        "analysis": _analysis(), "fix_diff": "+requests==2.31.0",
    })
    assert "verified fix" in body.lower()
    assert "```diff" in body and "+requests==2.31.0" in body
    assert "suggestion" in body.lower()  # never claims autonomy


def test_diagnosis_only_never_claims_a_fix():
    body = render_comment({"outcome": "diagnosis_only", "analysis": _analysis()})
    assert "```diff" not in body
    assert "did **not** produce a fix" in body


def test_failed_has_no_diff_and_no_fix_language():
    body = render_comment({"outcome": "failed", "analysis": None,
                           "analysis_error": "malformed JSON x3"})
    assert "```diff" not in body
    assert "could not" in body.lower()
    assert "malformed JSON" in body  # reason surfaced, clipped


def test_flaky_reports_ratio_not_a_patch():
    body = render_comment({
        "outcome": "flaky_detected", "analysis": _analysis(category="flaky_test"),
        "flaky_pass_count": 3, "repro_results": [1, 2, 3, 4, 5],
    })
    assert "3/5" in body
    assert "```diff" not in body


def test_model_prose_is_clipped_and_labelled():
    """SR-12: injected 1MB explanation cannot bloat the comment or read as CIDRA's."""
    body = render_comment({
        "outcome": "diagnosis_only",
        "analysis": _analysis(evidence="LEAK" * 100_000, proposed_action="x"),
    })
    assert len(body) < MAX_PROSE * 3
    assert "untrusted" in body.lower()
    assert "truncated" in body


def test_verified_diff_is_capped():
    body = render_comment({
        "outcome": "verified_fix", "verified": True, "analysis": _analysis(),
        "fix_diff": "+x\n" * 100_000,
    })
    assert len(body) < MAX_DIFF + 2000
    assert "truncated" in body


def test_marker_present_for_idempotent_update():
    assert _MARKER in render_comment({"outcome": "failed", "analysis": None})


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok  ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} passed")
    sys.exit(0)
