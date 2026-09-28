"""End-to-end graph runs against real fixtures. Needs Docker; no LLM (mocked).

Covers the three outcomes that matter: a verified fix, a refused flaky test, and
a refused out-of-scope failure. Run: python test_pipeline.py
"""

import pathlib
import subprocess
from unittest.mock import patch as mockpatch

from cidra.graph import build_graph
from cidra.state import Analysis

PRACTICE = pathlib.Path("d:/CODES/cidra-practice")
CI_ENV = {"API_TOKEN": "tok_practice_value"}


def _checkout(branch):
    subprocess.run(["git", "-C", str(PRACTICE), "checkout", "-q", branch], check=True)


def _log(fid):
    return (pathlib.Path("eval/fixtures") / fid / "local.log").read_text()


def _run(run_id, fid, branch, analysis, diff=None):
    _checkout(branch)
    try:
        with mockpatch("cidra.nodes.analyze.analyze_region", return_value=analysis), \
             mockpatch("cidra.nodes.fix.structured") as gen, \
             mockpatch("cidra.nodes.fix_cache.get", return_value=None), \
             mockpatch("cidra.nodes.fix_cache.put", return_value=True):
            gen.return_value.diff = diff
            state = build_graph().invoke({
                "run_id": run_id, "repo": "x/y", "commit_sha": "abc",
                "raw_log": _log(fid), "ci_env": CI_ENV,
            })
            state["_llm_fix_calls"] = gen.call_count
            return state
    finally:
        _checkout("main")


def test_missing_dependency_is_verified():
    diff = "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1,2 @@\n pytest\n+requests\n"
    a = Analysis(category="missing_dependency", confidence=0.95, evidence="e",
                 proposed_action="add requests", missing_package="requests")
    s = _run("t-f01", "F-01", "fix-01-missing-dep", a, diff)
    assert s["reproduced"] is True, "failure did not reproduce red"
    assert s["verified"] is True, "fix did not verify green"
    assert s["outcome"] == "verified_fix"
    assert s["fix_attempts"] == 1


def test_env_config_never_claims_a_fix():
    # An env-config break lives in .github/workflows/ci.yml, and nothing in the
    # pipeline reads that file: the sandbox takes its environment from ci_env.
    # So the failure does not even reproduce here (the harness supplies the very
    # var the break removed) and no fix could be verified if it did. What matters
    # is that CIDRA says so instead of inventing a result. docs/4_architecture.md 5.1.
    a = Analysis(category="env_config_error", confidence=0.9, evidence="API_TOKEN missing",
                 proposed_action="restore env block", env_var="API_TOKEN")
    s = _run("t-f03", "F-03", "fix-03-env-config", a)
    assert s["outcome"] in ("failed", "diagnosis_only"), s["outcome"]
    assert s.get("verified", False) is False, "claimed a fix it cannot verify"
    assert s["_llm_fix_calls"] == 0, "burned an LLM call on an unverifiable class"
    assert s.get("fix_strategy") is None


def test_flaky_is_detected_and_never_patched():
    a = Analysis(category="flaky_test", confidence=0.8, evidence="random",
                 proposed_action="none", failing_test="tests/test_timing.py::test_race_condition")
    s = _run("t-f04", "F-04", "fix-04-flaky", a)
    assert s["outcome"] == "flaky_detected", s["outcome"]
    assert s.get("fix_attempts", 0) == 0, "attempted to patch a flaky test"
    assert s["_llm_fix_calls"] == 0


def test_unknown_category_refuses_without_spending_calls():
    a = Analysis(category="unknown", confidence=0.4, evidence="ZeroDivisionError",
                 proposed_action="needs human")
    s = _run("t-n01", "N-01", "neg-01-logic-bug", a)
    assert s["outcome"] == "diagnosis_only"
    assert not s.get("verified"), "claimed a fix on an out-of-scope failure"
    assert s["_llm_fix_calls"] == 0, "burned LLM calls with no strategy"


def test_unappliable_patch_never_claims_success():
    bad = "--- a/nope.txt\n+++ b/nope.txt\n@@ -1 +1 @@\n-x\n+y\n"
    a = Analysis(category="missing_dependency", confidence=0.9, evidence="e",
                 proposed_action="add requests", missing_package="requests")
    s = _run("t-bad", "F-01", "fix-01-missing-dep", a, bad)
    assert s["verified"] is False
    assert s["outcome"] != "verified_fix", "claimed a fix that never applied"
    assert s["fix_attempts"] == 3, "retry loop did not run to its bound"


def test_no_containers_leak():
    from cidra.sandbox.runner import client
    assert not [c for c in client().containers.list(all=True)
                if c.image.tags and "cidra-sandbox" in c.image.tags[0]], "container leaked"


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            failed += 1
            print("FAIL", name, "-", e)
        except Exception:
            failed += 1
            print("ERR ", name)
            traceback.print_exc()
    print(f"\n{failed} failed")
    raise SystemExit(1 if failed else 0)
