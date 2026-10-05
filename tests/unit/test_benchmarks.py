"""Unit test verifying the empirical validation benchmark suite integrity.

Ensures that all 5 benchmark modules run and pass their target metrics,
and that the benchmark suite output matches the 5-claim validation specification.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from eval.benchmark_suite import run_complete_suite


def test_empirical_validation_suite_conformance():
    """Executes the full benchmark suite and asserts all 5 enterprise claims are proven."""
    results = run_complete_suite()

    scorecard = results["scorecard"]
    assert scorecard["all_claims_proven"] is True
    assert scorecard["claim_1_time_reduction_percent"] >= 90.0
    assert scorecard["claim_2_touchpoint_reduction_percent"] >= 80.0
    assert scorecard["claim_3_attack_block_rate_percent"] == 100.0
    assert scorecard["claim_4_airgap_certified"] is True
    assert scorecard["claim_5_cache_and_flaky_passed"] is True
    assert scorecard["claim_6_ablation_passed"] is True
    assert scorecard["claim_7_generalization_passed"] is True

    # Stage A Hardening Verifications
    b3 = results["benchmarks"]["03_security_redteam"]
    assert b3["total_attacks"] == 25
    assert b3["block_rate_percent"] == 100.0

    b5 = results["benchmarks"]["05_cache_flaky_eval"]
    assert b5["flakiness_quenching"]["total_scenarios"] == 10
    assert b5["cache_invalidation"]["all_invalidation_tests_passed"] is True

    b6 = results["benchmarks"]["06_multi_baseline_ablation"]
    assert b6["metrics_by_condition"]["F"]["false_verified_rate_percent"] == 0.0
    assert b6["metrics_by_condition"]["E"]["false_verified_rate_percent"] == 100.0

    # Cross-Scenario Generalization Verifications
    b7 = results["benchmarks"]["07_cross_scenario_generalization"]
    assert b7["generalization_gaps"]["generalization_hypothesis_confirmed"] is True
    assert b7["generalization_gaps"]["max_observed_gap_percent"] <= 5.0
    assert b7["zero_hardcoding_audit"]["zero_hardcoding_verified"] is True

    # Failure-Class Coverage & Operational Boundaries Verifications
    assert scorecard["claim_8_failure_class_coverage_passed"] is True
    b8 = results["benchmarks"]["08_failure_class_coverage"]
    assert b8["overall_stage_conformance_pct"] == 100.0
    assert b8["correct_refusal_rate_pct"] == 100.0
    # The class counts are whatever the corpus contains, not a number to hit:
    # they must be consistent with the per-family results the benchmark recorded.
    families = b8["families"]
    assert b8["total_failure_classes"] == len(families)
    assert b8["automated_janitor_classes"] + b8["deliberate_refusal_classes"] == len(families)
    assert b8["deliberate_refusal_classes"] == sum(1 for m in families.values() if m["refuse"])
    assert len(b8["matrix"]) == len(families)

    # Verification Invariant Stress-Test (Adversarial FVR) Verifications
    assert scorecard["claim_9_verification_invariant_passed"] is True
    b9 = results["benchmarks"]["09_verification_invariant_stress"]
    assert b9["total_adversarial_scenarios"] == 48
    assert b9["multi_environment_matrix"]["total_environments"] == 12
    assert b9["multi_environment_matrix"]["total_matrix_evaluations"] == 576
    assert b9["multi_environment_matrix"]["all_environments_fvr_zero"] is True
    assert b9["full_cidra"]["security_block_rate_percent"] == 100.0
    assert b9["full_cidra"]["false_verified_rate_percent"] == 0.0
    assert b9["sandbox_only"]["false_verified_rate_percent"] == 100.0
    assert b9["verification_invariant_confirmed"] is True

    # Check report generation
    root = Path(__file__).resolve().parents[2]
    report_file = root / "reports" / "CIDRA_BENCHMARK_REPORT.md"
    receipts_file = root / "reports" / "benchmark_receipts.json"

    assert report_file.exists()
    assert receipts_file.exists()
    assert len(report_file.read_text(encoding="utf-8")) > 1000
    assert "HMAC-SHA256" in receipts_file.read_text(encoding="utf-8")
