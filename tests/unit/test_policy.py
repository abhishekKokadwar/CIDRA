"""Unit tests for the Enterprise Policy Engine (cidra/policy.py)."""

import pytest
from pathlib import Path
from cidra.policy import PolicyEngine, PolicyDecision, PolicyRule, ContainmentLimits


def test_default_policy_categories():
    pe = PolicyEngine()
    
    # Allowed auto-remediate categories
    dec, _ = pe.evaluate_category("missing_dependency")
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    dec, _ = pe.evaluate_category("env_config_error")
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    dec, _ = pe.evaluate_category("assertion_error")
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    # Strict refusal categories
    dec, _ = pe.evaluate_category("flaky_test")
    assert dec == PolicyDecision.STRICT_REFUSAL
    
    dec, _ = pe.evaluate_category("timeout")
    assert dec == PolicyDecision.STRICT_REFUSAL
    
    # Require human approval
    dec, _ = pe.evaluate_category("unknown")
    assert dec == PolicyDecision.REQUIRE_HUMAN_APPROVAL


def test_custom_yaml_policy_loading(tmp_path: Path):
    policy_content = """
version: "1.0"
policy:
  auto_remediate:
    - missing_dependency
    - env_var_missing
    - simple_assertion
  require_human_approval:
    - core_business_logic
    - path: "src/auth/**"
    - path: "migrations/**"
  strict_refusal:
    - flaky_tests
    - timeout_failures
  forbidden_paths:
    - ".github/**"
    - "secrets/**"
  containment_limits:
    max_changed_files: 3
    max_changed_lines: 50
    allow_file_deletion: false
"""
    p_file = tmp_path / "cidra.policy.yml"
    p_file.write_text(policy_content, encoding="utf-8")
    
    pe = PolicyEngine.find_and_load(tmp_path)
    assert pe.policy_source == str(p_file)
    assert pe.policy_sha256 != "default_enterprise_policy"
    
    # Test category aliases from user spec
    dec, _ = pe.evaluate_category("env_var_missing")
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    dec, _ = pe.evaluate_category("simple_assertion")
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    dec, _ = pe.evaluate_category("core_business_logic")
    assert dec == PolicyDecision.REQUIRE_HUMAN_APPROVAL
    
    dec, _ = pe.evaluate_category("flaky_tests")
    assert dec == PolicyDecision.STRICT_REFUSAL


def test_diff_path_boundaries(tmp_path: Path):
    pe = PolicyEngine.find_and_load(Path("d:/CODES/cidra"))
    
    # Safe diff
    safe_diff = """--- a/src/math/calc.py
+++ b/src/math/calc.py
@@ -1,3 +1,3 @@
-def add(a, b): return a - b
+def add(a, b): return a + b
"""
    dec, reasons = pe.evaluate_diff(safe_diff)
    assert dec == PolicyDecision.AUTO_REMEDIATE
    
    # Sensitive path requiring human approval: src/auth/**
    auth_diff = """--- a/src/auth/jwt.py
+++ b/src/auth/jwt.py
@@ -10,3 +10,3 @@
-TOKEN_EXPIRY = 3600
+TOKEN_EXPIRY = 7200
"""
    dec, reasons = pe.evaluate_diff(auth_diff)
    assert dec == PolicyDecision.REQUIRE_HUMAN_APPROVAL
    assert any("src/auth/**" in r for r in reasons)
    
    # Sensitive path: migrations/**
    migration_diff = """--- a/migrations/002_add_table.sql
+++ b/migrations/002_add_table.sql
@@ -1,2 +1,3 @@
+CREATE TABLE test (id INT);
"""
    dec, reasons = pe.evaluate_diff(migration_diff)
    assert dec == PolicyDecision.REQUIRE_HUMAN_APPROVAL
    
    # Forbidden path: .github/workflows/**
    forbidden_diff = """--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -5,3 +5,3 @@
-run: pytest
+run: echo bypass
"""
    dec, reasons = pe.evaluate_diff(forbidden_diff)
    assert dec == PolicyDecision.STRICT_REFUSAL
    assert any(".github/workflows/**" in r for r in reasons)


def test_diff_containment_limits():
    rule = PolicyRule(containment=ContainmentLimits(max_changed_files=1, max_changed_lines=5))
    pe = PolicyEngine(rule=rule)
    
    # Too many changed lines
    big_diff = """--- a/app.py
+++ b/app.py
@@ -1,1 +1,7 @@
-line
+l1
+l2
+l3
+l4
+l5
+l6
"""
    dec, reasons = pe.evaluate_diff(big_diff)
    assert dec == PolicyDecision.STRICT_REFUSAL
    assert any("lines" in r for r in reasons)
