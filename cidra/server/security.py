"""Webhook signature verification. Phase 7, step 7.1.

Zone-1 enforcement (docs/4_architecture.md §2, docs/threat/threat_model.md):
a webhook payload is untrusted until its HMAC proves it came from GitHub with
our shared secret. This runs BEFORE anything parses the body, so a spoofed
payload can never make CIDRA spawn a container.

GitHub signs the RAW request body with HMAC-SHA256 and sends
`X-Hub-Signature-256: sha256=<hex>`. The signature must be computed over the
exact bytes received — re-serialising the JSON would change them and break the
match — and compared in constant time so a timing side-channel can't leak it.
"""

import hashlib
import hmac

SIGNATURE_HEADER = "X-Hub-Signature-256"


def verify_signature(body: bytes, header: str | None, secret: str) -> bool:
    """True iff `header` is a valid sha256 HMAC of `body` under `secret`.

    Fails closed: a missing secret, missing/malformed header, or any mismatch
    returns False. Never raises on bad input — the caller turns False into 401.
    """
    if not secret or not header:
        return False
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    got = header[len("sha256="):]
    return hmac.compare_digest(expected, got)


def sign(body: bytes, secret: str) -> str:
    """Produce the header value for a body — used by tests and local tooling."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
