"""Unit tests for the Cryptographic Audit Manifest (cidra/audit_manifest.py)."""

import pytest
import json
from pathlib import Path
from cidra.state import DebugState, Analysis, SandboxResult
from cidra.policy import PolicyEngine, PolicyDecision
from cidra.audit_manifest import generate_manifest, verify_manifest, save_manifest


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    # Signing needs an operator key; there is no built-in default.
    monkeypatch.setenv("CIDRA_AUDIT_SIGNING_KEY", "test-signing-key")


def test_manifest_is_unsigned_without_an_operator_key(monkeypatch):
    monkeypatch.delenv("CIDRA_AUDIT_SIGNING_KEY")
    manifest = generate_manifest({"run_id": "r", "repo": "o/r", "commit_sha": "abc"})
    assert manifest.seal.algorithm == "none" and manifest.seal.signature == ""
    assert verify_manifest(manifest.to_dict()) is False  # nothing to verify against


def test_audit_manifest_generation():
    state: DebugState = {
        "run_id": "test_run_123",
        "repo": "enterprise/payments-api",
        "commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
        "raw_log": "ImportError: No module named 'requests'",
        "error_region": "ModuleNotFoundError: No module named 'requests'",
        "analysis": Analysis(
            category="missing_dependency",
            confidence=0.98,
            evidence="No module named 'requests'",
            proposed_action="Add requests to requirements.txt",
            missing_package="requests"
        ),
        "fix_diff": "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1,1 +1,2 @@\n+requests>=2.31.0\n",
        "patch_audit_ok": True,
        "patch_audit_reasons": [],
        "verified": True,
        "verify_results": [
            SandboxResult(
                step="verify",
                exit_code=0,
                stdout_tail="12 passed in 1.1s",
                stderr_tail="",
                duration_s=1.2,
                timed_out=False
            )
        ]
    }

    pe = PolicyEngine()
    manifest = generate_manifest(state, pe)

    assert manifest.manifest_id.startswith("man_")
    assert manifest.target.repo == "enterprise/payments-api"
    assert manifest.target.run_id == "test_run_123"
    assert manifest.policy.decision == "auto_remediate"
    assert manifest.security.ast_audit_passed is True
    assert manifest.sandbox.network_egress_bytes == 0
    assert manifest.sandbox.verification_passed is True
    assert manifest.seal is not None
    assert manifest.seal.algorithm == "HMAC-SHA256"

    # Verify signature passes on unmodified manifest
    manifest_dict = manifest.to_dict()
    assert verify_manifest(manifest_dict) is True


def test_audit_manifest_tamper_detection():
    state: DebugState = {
        "run_id": "run_456",
        "repo": "enterprise/crypto-vault",
        "commit_sha": "1234567890abcdef",
        "raw_log": "AssertionError: expected 200 got 500",
        "verified": False
    }

    manifest = generate_manifest(state)
    manifest_dict = manifest.to_dict()

    # Original passes verification
    assert verify_manifest(manifest_dict) is True

    # Tampering test 1: Modify sandbox isolation claim
    tampered_1 = json.loads(json.dumps(manifest_dict))
    tampered_1["sandbox"]["network_egress_bytes"] = 1024
    assert verify_manifest(tampered_1) is False

    # Tampering test 2: Modify policy decision
    tampered_2 = json.loads(json.dumps(manifest_dict))
    tampered_2["policy"]["decision"] = "auto_remediate"
    assert verify_manifest(tampered_2) is False

    # Tampering test 3: Modify diff hash
    tampered_3 = json.loads(json.dumps(manifest_dict))
    tampered_3["evidence"]["patch_diff_sha256"] = "badhash"
    assert verify_manifest(tampered_3) is False


def test_save_audit_manifest(tmp_path: Path):
    state: DebugState = {
        "run_id": "run_save_test",
        "repo": "org/repo",
        "commit_sha": "abcdef123",
    }
    manifest = generate_manifest(state)
    out_file = tmp_path / "test_manifest.json"
    
    saved = save_manifest(manifest, out_file)
    assert saved.is_file()
    
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert verify_manifest(loaded) is True
