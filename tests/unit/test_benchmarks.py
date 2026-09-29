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

    # Check report generation
    root = Path(__file__).resolve().parents[2]
    report_file = root / "reports" / "CIDRA_BENCHMARK_REPORT.md"
    receipts_file = root / "reports" / "benchmark_receipts.json"

    assert report_file.exists()
    assert receipts_file.exists()
    assert len(report_file.read_text(encoding="utf-8")) > 1000
    assert "HMAC-SHA256" in receipts_file.read_text(encoding="utf-8")
