"""Phase 11.1 — failure fingerprinting: stable across noise, sensitive to signal."""

from cidra.nodes.fingerprint import normalize, fingerprint


def test_empty_is_empty():
    assert fingerprint("") == "" and fingerprint("   \n") == ""


def test_same_failure_same_fingerprint():
    a = "Traceback\n  File 'x.py', line 12\nModuleNotFoundError: No module named 'requests'"
    b = "Traceback\n  File 'x.py', line 12\nModuleNotFoundError: No module named 'requests'"
    assert fingerprint(a) == fingerprint(b)


def test_line_numbers_do_not_change_fingerprint():
    a = "File 'x.py', line 12\nAssertionError: 4 == 5"
    b = "File 'x.py', line 99\nAssertionError: 4 == 5"
    assert fingerprint(a) == fingerprint(b)


def test_memory_address_ignored():
    a = "<Foo object at 0x7f001122>\nValueError: bad"
    b = "<Foo object at 0xdeadbeef>\nValueError: bad"
    assert fingerprint(a) == fingerprint(b)


def test_temp_paths_and_timestamps_ignored():
    a = "2026-09-21 10:00:00 /tmp/pytest-123/t.py FAILED"
    b = "2026-09-22 11:22:33 /tmp/pytest-987/t.py FAILED"
    assert fingerprint(a) == fingerprint(b)


def test_different_error_type_differs():
    a = "ValueError: bad input"
    b = "KeyError: bad input"
    assert fingerprint(a) != fingerprint(b)


def test_different_message_differs():
    a = "ModuleNotFoundError: No module named 'requests'"
    b = "ModuleNotFoundError: No module named 'numpy'"
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_is_hex_sha256():
    fp = fingerprint("ValueError: x")
    assert len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)


def test_normalize_collapses_whitespace():
    assert "  " not in normalize("a\n\n   b\t\tc")
