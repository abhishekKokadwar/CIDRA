"""Phase 11.2 — verified-fix cache store."""

from cidra.nodes import fix_cache


def test_put_then_get_roundtrip(tmp_path):
    p = tmp_path / "c.json"
    assert fix_cache.put("fp1", "+requests", "missing_dependency", path=p)
    entry = fix_cache.get("fp1", path=p)
    assert entry["diff"] == "+requests" and entry["category"] == "missing_dependency"


def test_miss_returns_none(tmp_path):
    assert fix_cache.get("nope", path=tmp_path / "c.json") is None


def test_empty_fingerprint_never_hits_or_writes(tmp_path):
    p = tmp_path / "c.json"
    assert fix_cache.put("", "+x", "cat", path=p) is False
    assert fix_cache.get("", path=p) is None


def test_empty_diff_is_refused(tmp_path):
    assert fix_cache.put("fp", "", "cat", path=tmp_path / "c.json") is False


def test_persists_across_reload(tmp_path):
    p = tmp_path / "c.json"
    fix_cache.put("fp1", "+a", "cat", path=p)
    # a fresh call re-reads the file (no in-memory state)
    assert fix_cache.get("fp1", path=p)["diff"] == "+a"


def test_meta_is_stored(tmp_path):
    p = tmp_path / "c.json"
    fix_cache.put("fp1", "+a", "cat", meta={"run_id": "r1"}, path=p)
    assert fix_cache.get("fp1", path=p)["run_id"] == "r1"


def test_corrupt_cache_is_a_miss_not_a_crash(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{ not json", encoding="utf-8")
    assert fix_cache.get("fp1", path=p) is None
    # and a put over a corrupt file still succeeds (overwrites)
    assert fix_cache.put("fp1", "+a", "cat", path=p) is True
