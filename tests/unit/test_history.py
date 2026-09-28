"""Phase 13.1/13.2 — run-history store + record-on-cleanup."""

from cidra import history
from cidra.nodes import publish
from cidra.state import Analysis


def _state(**kw):
    base = {"run_id": "r1", "repo": "o/r", "commit_sha": "abcdef1234567890",
            "outcome": "verified_fix", "verified": True,
            "analysis": Analysis(category="missing_dependency", confidence=0.9,
                                 evidence="e", proposed_action="p")}
    base.update(kw)
    return base


def test_summarize_is_flat_and_has_no_secrets():
    row = history.summarize(_state(comment_url="https://gh/c/1"))
    assert row["outcome"] == "verified_fix" and row["category"] == "missing_dependency"
    assert row["commit_sha"] == "abcdef123456"  # truncated
    # nothing heavy/secret leaks into the index
    assert "raw_log" not in row and "fix_diff" not in row and "analysis" not in row


def test_record_then_load_roundtrip(tmp_path):
    p = tmp_path / "h.jsonl"
    assert history.record(_state(run_id="a"), path=p)
    assert history.record(_state(run_id="b"), path=p)
    rows = history.load(path=p)
    assert [r["run_id"] for r in rows] == ["b", "a"]  # newest first


def test_load_respects_limit(tmp_path):
    p = tmp_path / "h.jsonl"
    for i in range(5):
        history.record(_state(run_id=str(i)), path=p)
    assert [r["run_id"] for r in history.load(limit=2, path=p)] == ["4", "3"]


def test_load_missing_file_is_empty(tmp_path):
    assert history.load(path=tmp_path / "nope.jsonl") == []


def test_corrupt_line_is_skipped(tmp_path):
    p = tmp_path / "h.jsonl"
    history.record(_state(run_id="good"), path=p)
    with p.open("a", encoding="utf-8") as f:
        f.write("{ not json\n")
    rows = history.load(path=p)
    assert len(rows) == 1 and rows[0]["run_id"] == "good"


def test_cleanup_records_the_run(tmp_path, monkeypatch):
    p = tmp_path / "h.jsonl"
    monkeypatch.setattr(history.config, "RUN_HISTORY_PATH", str(p))
    # cleanup also tears down session/checkout; those are no-ops here.
    monkeypatch.setattr("cidra.nodes.environment.close_session", lambda rid: None)
    monkeypatch.setattr("cidra.nodes.checkout.remove_checkout", lambda rid: None)
    publish.cleanup(_state(run_id="viaCleanup"))
    rows = history.load(path=p)
    assert rows and rows[0]["run_id"] == "viaCleanup"
