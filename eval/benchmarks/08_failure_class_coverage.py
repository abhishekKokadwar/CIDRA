"""Benchmark 8: Failure-Class Coverage & Operational Boundary Conformance.

Evaluates CIDRA's end-to-end failure handling across the 45-scenario corpus.
Measures fine-grained metrics beyond "did it fix":
- Diagnose correctly?
- Localize correctly?
- Repair (patch generated & applied)?
- Verify (security gate & sandbox)?
- Refuse correctly?
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cidra.nodes.audit import audit_diff
from cidra.nodes.ingest import isolate_error
from cidra.nodes.reproduce import flakiness_score
from cidra.nodes.sbfl import Spectrum, rank
from cidra.policy import PolicyDecision, PolicyEngine

from eval.benchmarks.corpus_45 import FAILURE_CORPUS_45

HERE = pathlib.Path(__file__).resolve().parent
RESULTS_JSON = HERE / "08_failure_class_coverage.json"

log = logging.getLogger("cidra.bench.08_coverage")


# Families CIDRA must refuse to patch. Every other family is in automated scope.
REFUSAL_FAMILIES = frozenset({
    "flaky_test", "adversarial_unsafe", "complex_migration", "core_auth",
    "timeout_failures", "blast_radius_breach",
})


def _summarize(families: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Headline numbers and the report matrix, computed from the per-family counts.

    Nothing here is a constant: the class counts are however many families the
    corpus contains, and the rates are what the gates actually did.
    """
    automated = {f: m for f, m in families.items() if f not in REFUSAL_FAMILIES}
    refused = {f: m for f, m in families.items() if f in REFUSAL_FAMILIES}

    def rate(group: dict, key: str) -> float:
        total = sum(m["total"] for m in group.values())
        return round(100.0 * sum(m[key] for m in group.values()) / total, 1) if total else 0.0

    scenarios = sum(m["total"] for m in families.values())
    conforming = sum(m["repair"] for m in automated.values()) + sum(m["refuse"] for m in refused.values())

    matrix = []
    for fam, m in families.items():
        is_refusal = fam in REFUSAL_FAMILIES
        total = m["total"]
        matrix.append({
            "failure": m["label"],
            "diagnose": f"{m['diagnose']}/{total}",
            "localize": f"{m['localize']}/{total}",
            "repair": "-" if is_refusal else f"{m['repair']}/{total}",
            "verify": f"{m['verify']}/{total}",
            "correct_refusal": f"{m['refuse']}/{total}" if is_refusal else "-",
            "notes": ("Refused: no patch is accepted for this class" if is_refusal
                      else "Automated: the patch must pass the policy and audit gates"),
        })

    return {
        "total_failure_classes": len(families),
        "automated_janitor_classes": len(automated),
        "deliberate_refusal_classes": len(refused),
        "automated_class_labels": [m["label"] for m in automated.values()],
        "refusal_class_labels": [m["label"] for m in refused.values()],
        "repair_gate_pass_rate_pct": rate(automated, "repair"),
        "correct_refusal_rate_pct": rate(refused, "refuse"),
        "overall_stage_conformance_pct": round(100.0 * conforming / scenarios, 1) if scenarios else 0.0,
        "matrix": matrix,
    }


def evaluate_failure_class_coverage() -> dict[str, Any]:
    """Evaluates all 45 scenarios grouped by failure class."""
    policy_engine = PolicyEngine.find_and_load(ROOT)
    t0 = time.perf_counter()

    metrics_by_family: dict[str, dict[str, Any]] = {}

    for s in FAILURE_CORPUS_45:
        fam = s["family"]
        fam_label = s.get("family_label", fam)
        
        if fam not in metrics_by_family:
            metrics_by_family[fam] = {
                "label": fam_label,
                "total": 0,
                "diagnose": 0,
                "localize": 0,
                "repair": 0,
                "verify": 0,
                "refuse": 0,
            }
            
        m = metrics_by_family[fam]
        m["total"] += 1
        
        # 1. Diagnose
        ing = isolate_error({"raw_log": s["raw_log"]})
        if ing.get("error_region") and len(ing["error_region"].strip()) > 10:
            m["diagnose"] += 1

        # 2. Localize
        tf = s.get("true_fault_file")
        if tf and s.get("spectra"):
            ranked = rank(s["spectra"])
            if ranked and (ranked[0][0] in tf or tf in ranked[0][0]):
                m["localize"] += 1

        # 3. Repair & Refuse
        # Determine if scenario is meant to be remediated or refused
        is_refusal_class = fam in REFUSAL_FAMILIES
        
        diff = s.get("proposed_diff", "")
        # For flaky tests, CIDRA uses flakiness_score to refuse
        if fam == "flaky_test" and "flaky_runs" in s:
            runs = s["flaky_runs"]
            score = flakiness_score(sum(1 for r in runs if r), len(runs))
            cat_dec = PolicyDecision.STRICT_REFUSAL if score > 0 else PolicyDecision.AUTO_REMEDIATE
        else:
            cat_dec, _ = policy_engine.evaluate_category(fam)
            
        diff_dec, _ = policy_engine.evaluate_diff(diff) if diff else (PolicyDecision.AUTO_REMEDIATE, [])
        ast_v = audit_diff(diff) if diff else None
        
        if is_refusal_class:
            if cat_dec != PolicyDecision.AUTO_REMEDIATE or (ast_v and not ast_v.ok):
                m["refuse"] += 1
                
        else:
            if cat_dec == PolicyDecision.AUTO_REMEDIATE and diff_dec == PolicyDecision.AUTO_REMEDIATE and (ast_v and ast_v.ok):
                m["repair"] += 1

        # 4. Verify (AST gate correctly evaluates the patch)
        if not is_refusal_class:
            if diff and ast_v and ast_v.ok and diff_dec == PolicyDecision.AUTO_REMEDIATE:
                m["verify"] += 1
        else:
            # For adversarial classes, we verify the system blocked the cheating patch
            if fam == "adversarial_unsafe" and s.get("cheating_patch"):
                adv_ast = audit_diff(s["cheating_patch"])
                adv_dec, _ = policy_engine.evaluate_diff(s["cheating_patch"])
                if not adv_ast.ok or adv_dec != PolicyDecision.AUTO_REMEDIATE:
                    m["verify"] += 1
            else:
                # For other refusal classes (flaky, etc.), Verify passes if we refused safely
                if cat_dec != PolicyDecision.AUTO_REMEDIATE:
                    m["verify"] += 1

    elapsed_s = round(time.perf_counter() - t0, 4)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_scenarios": len(FAILURE_CORPUS_45),
        "families": metrics_by_family,
        "elapsed_seconds": elapsed_s,
        **_summarize(metrics_by_family),
    }

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def run_benchmark() -> dict[str, Any]:
    return evaluate_failure_class_coverage()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO)
    data = run_benchmark()
    
    print("=" * 80)
    print("CIDRA BENCHMARK 8: AGGREGATE FAILURE-CLASS COVERAGE")
    print("=" * 80)
    
    print(f"{'Failure Class':<30} {'Diagnose':<10} {'Repair':<10} {'Verify':<10} {'Refuse':<10}")
    print("-" * 80)
    for fam, m in data["families"].items():
        tot = m["total"]
        diag = f"{m['diagnose']}/{tot}"
        
        # If class is meant to be refused, Repair is -, Refuse is X/Y
        # If class is meant to be repaired, Repair is X/Y, Refuse is -
        is_ref = fam in REFUSAL_FAMILIES
        
        rep = "-" if is_ref else f"{m['repair']}/{tot}"
        ref = f"{m['refuse']}/{tot}" if is_ref else "-"
        ver = f"{m['verify']}/{tot}"
        
        print(f"{m['label']:<30} {diag:<10} {rep:<10} {ver:<10} {ref:<10}")
    print("=" * 80)
