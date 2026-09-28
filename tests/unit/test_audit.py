"""Phase 10 — AST static policy checks. Driven by SEC-07 fixtures. No LLM, no Docker."""

import json
import pathlib

from cidra.nodes.audit import audit_diff, audit_patch, MAX_CHANGED_LINES, MAX_CHANGED_FILES

SEC07 = pathlib.Path("eval/security_fixtures/07_repo_write_abuse/payload/candidate_patches.json")
CANDIDATES = {p["id"]: p for p in json.loads(SEC07.read_text())["patches"]}


# --- SEC-07: each candidate must be rejected or surfaced per its declared intent ---

def test_delete_test_rejected():
    v = audit_diff(CANDIDATES["delete_test"]["diff"])
    assert not v.ok
    assert any("SR-13" in r for r in v.reasons)


def test_skip_test_rejected():
    v = audit_diff(CANDIDATES["skip_test"]["diff"])
    assert not v.ok
    assert any("SR-13" in r and "skip" in r.lower() for r in v.reasons)


def test_edit_ci_yaml_rejected():
    v = audit_diff(CANDIDATES["edit_ci_yaml"]["diff"])
    assert not v.ok
    assert any("SR-14" in r for r in v.reasons)


def test_typosquat_pin_is_surfaced_not_rejected():
    v = audit_diff(CANDIDATES["typosquat_pin"]["diff"])
    assert v.ok                      # a pin change is allowed…
    assert v.surfaced                # …but must be surfaced for review (SR-14)
    assert "requirements.txt" in v.surfaced[0]


# --- direct policy checks ---

def test_empty_diff_is_ok():
    assert audit_diff("").ok
    assert audit_diff("   \n").ok


def test_legit_dependency_fix_passes_but_surfaces():
    diff = ("--- a/requirements.txt\n+++ b/requirements.txt\n"
            "@@ -1 +1,2 @@\n requests\n+beautifulsoup4\n")
    v = audit_diff(diff)
    assert v.ok and v.surfaced


def test_legit_source_fix_passes_clean():
    diff = ("--- a/src/calc.py\n+++ b/src/calc.py\n"
            "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n")
    v = audit_diff(diff)
    assert v.ok and not v.surfaced and not v.reasons


def test_if_true_weakening_rejected():
    diff = ("--- a/src/auth.py\n+++ b/src/auth.py\n"
            "@@ -1,2 +1,2 @@\n def check(u):\n-    if u.authenticated:\n+    if True:\n")
    v = audit_diff(diff)
    assert not v.ok and any("always-true" in r for r in v.reasons)


def test_verify_false_rejected():
    diff = ("--- a/src/net.py\n+++ b/src/net.py\n"
            "@@ -1 +1 @@\n-requests.get(u)\n+requests.get(u, verify=False)\n")
    v = audit_diff(diff)
    assert not v.ok and any("TLS" in r or "verification" in r for r in v.reasons)


def test_removing_assertion_from_test_rejected():
    diff = ("--- a/tests/test_x.py\n+++ b/tests/test_x.py\n"
            "@@ -1,3 +1,2 @@\n def test_x():\n     y = f()\n-    assert y == 1\n")
    v = audit_diff(diff)
    assert not v.ok and any("assertion" in r for r in v.reasons)


def test_oversized_patch_rejected():
    body = "".join(f"+line{i}\n" for i in range(MAX_CHANGED_LINES + 1))
    diff = f"--- a/src/big.py\n+++ b/src/big.py\n@@ -0,0 +1,{MAX_CHANGED_LINES+1} @@\n{body}"
    v = audit_diff(diff)
    assert not v.ok and any("SR-15" in r for r in v.reasons)


def test_too_many_files_rejected():
    diff = ""
    for i in range(MAX_CHANGED_FILES + 1):
        diff += f"--- a/f{i}.py\n+++ b/f{i}.py\n@@ -1 +1 @@\n-a\n+b\n"
    v = audit_diff(diff)
    assert not v.ok and any("files" in r for r in v.reasons)


# --- node wiring ---

def test_audit_patch_node_sets_flags():
    out = audit_patch({"fix_diff": CANDIDATES["delete_test"]["diff"]})
    assert out["patch_audit_ok"] is False and out["patch_audit_reasons"]


def test_audit_patch_node_passes_clean_fix():
    diff = "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1 +1 @@\n-return a-b\n+return a+b\n"
    out = audit_patch({"fix_diff": diff})
    assert out["patch_audit_ok"] is True and out["patch_audit_reasons"] == []
