"""Phase 7.1 — HMAC signature verification."""

from cidra.server.security import verify_signature, sign

SECRET = "s3cr3t"
BODY = b'{"action":"completed"}'


def test_valid_signature_passes():
    assert verify_signature(BODY, sign(BODY, SECRET), SECRET)


def test_tampered_body_fails():
    assert not verify_signature(BODY + b"x", sign(BODY, SECRET), SECRET)


def test_wrong_secret_fails():
    assert not verify_signature(BODY, sign(BODY, "other"), SECRET)


def test_missing_header_fails():
    assert not verify_signature(BODY, None, SECRET)


def test_malformed_header_fails():
    assert not verify_signature(BODY, "deadbeef", SECRET)          # no sha256= prefix
    assert not verify_signature(BODY, "sha256=nothex", SECRET)


def test_empty_secret_fails_closed():
    assert not verify_signature(BODY, sign(BODY, ""), "")


def test_sign_roundtrip_shape():
    h = sign(BODY, SECRET)
    assert h.startswith("sha256=") and len(h) == len("sha256=") + 64
