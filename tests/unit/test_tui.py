"""Phase 13.3 — Fleet TUI rendering (pure, stdlib only)."""

from cidra import tui


def test_empty_history_message():
    assert "No CIDRA runs" in tui.render([])


def test_renders_headers_and_a_row():
    rows = [{"ts": 1_700_000_000, "repo": "o/r", "commit_sha": "abc123",
             "outcome": "verified_fix", "category": "missing_dependency",
             "comment_url": "https://gh/c/1"}]
    out = tui.render(rows)
    for h in ("when", "repo", "outcome", "class"):
        assert h in out
    assert "verified" in out and "missing_dependency" in out
    assert "comment" in out  # note derived from comment_url


def test_cache_hit_and_flaky_notes():
    rows = [
        {"ts": 1, "repo": "o/r", "outcome": "verified_fix", "cache_hit": True},
        {"ts": 2, "repo": "o/r", "outcome": "flaky_detected", "flaky_score": 80},
    ]
    out = tui.render(rows)
    assert "cached" in out
    assert "flaky" in out and "score 80" in out


def test_summary_line_counts():
    rows = [
        {"ts": 1, "repo": "a", "outcome": "verified_fix"},
        {"ts": 2, "repo": "b", "outcome": "verified_fix", "cache_hit": True},
        {"ts": 3, "repo": "c", "outcome": "failed"},
    ]
    out = tui.render(rows)
    assert "3 run(s)" in out and "2 verified" in out and "1 served from cache" in out


def test_main_prints_without_error(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(tui.history.config, "RUN_HISTORY_PATH", str(tmp_path / "none.jsonl"))
    assert tui.main(["--limit", "5"]) == 0
    assert "No CIDRA runs" in capsys.readouterr().out
