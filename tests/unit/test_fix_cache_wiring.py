"""Phase 11.3/11.4 — cache check in select_strategy, write in verify_fix, routing."""

from cidra.nodes import fix, fix_cache
from cidra.nodes.fingerprint import fingerprint
from cidra.state import Analysis, SandboxResult
from cidra import routers


def _analysis(cat="missing_dependency"):
    return Analysis(category=cat, confidence=0.9, evidence="e", proposed_action="p")


def test_select_strategy_computes_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setattr(fix_cache.config, "FIX_CACHE_PATH", str(tmp_path / "c.json"))
    out = fix.select_strategy({"analysis": _analysis(), "error_region": "ValueError: x"})
    assert out["fingerprint"] == fingerprint("ValueError: x")
    assert "cache_hit" not in out  # empty cache => miss


def test_select_strategy_reuses_cached_fix(monkeypatch, tmp_path):
    cache = tmp_path / "c.json"
    monkeypatch.setattr(fix_cache.config, "FIX_CACHE_PATH", str(cache))
    region = "ModuleNotFoundError: No module named 'requests'"
    fix_cache.put(fingerprint(region), "+requests", "missing_dependency", path=cache)

    out = fix.select_strategy({"analysis": _analysis(), "error_region": region})
    assert out["cache_hit"] is True and out["fix_diff"] == "+requests"


def test_cache_hit_skips_llm_via_router():
    out = {"fix_strategy": "append_requirement", "cache_hit": True, "fix_diff": "+r"}
    assert routers.route_after_strategy(out) == "audit_patch"   # NOT generate_fix


def test_verify_writes_cache_on_success(monkeypatch, tmp_path):
    cache = tmp_path / "c.json"
    monkeypatch.setattr(fix_cache.config, "FIX_CACHE_PATH", str(cache))

    green = SandboxResult(step="verify", exit_code=0, stdout_tail="", stderr_tail="",
                          duration_s=0.1, timed_out=False)

    class S:
        def run(self, *a, **k): return green
    monkeypatch.setattr(fix, "session_for", lambda rid: S())

    fp = fingerprint("boom")
    state = {"run_id": "r", "patch_applied": True, "fix_strategy": "patch_source",
             "fix_diff": "+fix", "fingerprint": fp, "analysis": _analysis("assertion_error"),
             "ci_env": {}}
    out = fix.verify_fix(state)
    assert out["verified"] is True
    assert fix_cache.get(fp, path=cache)["diff"] == "+fix"  # written


def test_verify_does_not_rewrite_on_cache_hit(monkeypatch, tmp_path):
    cache = tmp_path / "c.json"
    monkeypatch.setattr(fix_cache.config, "FIX_CACHE_PATH", str(cache))
    green = SandboxResult(step="verify", exit_code=0, stdout_tail="", stderr_tail="",
                          duration_s=0.1, timed_out=False)

    class S:
        def run(self, *a, **k): return green
    monkeypatch.setattr(fix, "session_for", lambda rid: S())

    state = {"run_id": "r", "patch_applied": True, "fix_strategy": "patch_source",
             "fix_diff": "+fix", "fingerprint": fingerprint("boom"), "cache_hit": True,
             "analysis": _analysis(), "ci_env": {}}
    fix.verify_fix(state)
    assert fix_cache.get(fingerprint("boom"), path=cache) is None  # nothing new learned


def test_verify_does_not_cache_a_failure(monkeypatch, tmp_path):
    cache = tmp_path / "c.json"
    monkeypatch.setattr(fix_cache.config, "FIX_CACHE_PATH", str(cache))
    red = SandboxResult(step="verify", exit_code=1, stdout_tail="", stderr_tail="",
                        duration_s=0.1, timed_out=False)

    class S:
        def run(self, *a, **k): return red
    monkeypatch.setattr(fix, "session_for", lambda rid: S())

    state = {"run_id": "r", "patch_applied": True, "fix_strategy": "patch_source",
             "fix_diff": "+bad", "fingerprint": fingerprint("boom"),
             "analysis": _analysis(), "ci_env": {}}
    out = fix.verify_fix(state)
    assert out["verified"] is False
    assert fix_cache.get(fingerprint("boom"), path=cache) is None  # never cache unverified
