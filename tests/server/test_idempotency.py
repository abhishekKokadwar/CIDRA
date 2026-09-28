"""Phase 7.2 — idempotency store."""

from cidra.server.idempotency import IdempotencyStore


def test_first_claim_true_duplicate_false(tmp_path):
    s = IdempotencyStore(tmp_path / "i.db")
    assert s.claim("run1", "shaA") is True
    assert s.claim("run1", "shaA") is False  # exact duplicate
    s.close()


def test_distinct_keys_are_independent(tmp_path):
    s = IdempotencyStore(tmp_path / "i.db")
    assert s.claim("run1", "shaA") is True
    assert s.claim("run1", "shaB") is True   # same run, different commit
    assert s.claim("run2", "shaA") is True   # different run, same commit
    s.close()


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "i.db"
    s = IdempotencyStore(path)
    assert s.claim("run1", "shaA") is True
    s.close()
    s2 = IdempotencyStore(path)               # simulate a restart
    assert s2.claim("run1", "shaA") is False  # still remembered
    s2.close()


def test_accepts_int_run_id(tmp_path):
    s = IdempotencyStore(tmp_path / "i.db")
    assert s.claim(12345, "shaA") is True
    assert s.claim("12345", "shaA") is False  # int and str collapse to same key
    s.close()
