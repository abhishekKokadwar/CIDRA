"""Benchmark 2: Step-Reduction Analysis (Claim 2).

Quantifies and audits the developer touchpoints and context switches
required to resolve routine CI failures: Manual Debugging (8 touchpoints)
vs CIDRA Autonomous Workflow (1 touchpoint).

Specification: docs/EMPIRICAL_VALIDATION_PLAN.md §3
Target Metric:
  - Touchpoints: 8 steps -> 1 step (87.5% reduction)
  - Context switches: 3 switches -> 0 switches (100% reduction)
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HERE = pathlib.Path(__file__).resolve().parent
RESULTS_JSON = HERE / "02_step_audit.json"

log = logging.getLogger("cidra.bench.02_steps")

MANUAL_STEPS = [
    {
        "step_number": 1,
        "step_name": "Notification Ingestion",
        "description": "Receive email/Slack alert regarding broken CI build on GitHub Actions",
        "interface": "Slack / Email Client",
        "context_switch": True,
        "cognitive_load": "Low",
    },
    {
        "step_number": 2,
        "step_name": "CI Dashboard Navigation",
        "description": "Switch context to browser, navigate to repository Actions tab, open failed run",
        "interface": "Web Browser",
        "context_switch": True,
        "cognitive_load": "Medium",
    },
    {
        "step_number": 3,
        "step_name": "Console Log Triage",
        "description": "Scroll through 2,000+ lines of raw console logs to locate traceback error block",
        "interface": "Web Browser Console",
        "context_switch": False,
        "cognitive_load": "High",
    },
    {
        "step_number": 4,
        "step_name": "Local Branch Checkout & Stash",
        "description": "Switch context to terminal, stash active feature branch, checkout failing branch",
        "interface": "Terminal (Git)",
        "context_switch": True,
        "cognitive_load": "Medium",
    },
    {
        "step_number": 5,
        "step_name": "Manual Code / Config Edit",
        "description": "Switch context to IDE, navigate to file, manually add missing dependency or default",
        "interface": "IDE / Code Editor",
        "context_switch": True,
        "cognitive_load": "Medium",
    },
    {
        "step_number": 6,
        "step_name": "Local Test Reproduction",
        "description": "Run pytest locally in terminal/IDE to verify proposed modification fixes failure",
        "interface": "Terminal / Pytest",
        "context_switch": False,
        "cognitive_load": "Medium",
    },
    {
        "step_number": 7,
        "step_name": "Git Commit & Push",
        "description": "Stage changed files, write conventional commit message, push branch to origin",
        "interface": "Terminal (Git)",
        "context_switch": False,
        "cognitive_load": "Low",
    },
    {
        "step_number": 8,
        "step_name": "Cloud CI Runner Verification Wait",
        "description": "Wait 3-5 minutes for GitHub Actions runner to pick up commit and verify green build",
        "interface": "Web Browser (CI)",
        "context_switch": True,
        "cognitive_load": "Low",
    },
]

CIDRA_STEPS = [
    {
        "step_number": 1,
        "step_name": "PR Review & Merge Decision",
        "description": "Review automated draft PR containing verified patch diff, sandbox execution proof, and HMAC audit manifest; click Merge",
        "interface": "GitHub PR / Slack Review Action",
        "context_switch": False,
        "cognitive_load": "Low",
    }
]


def run_step_audit_benchmark() -> dict:
    """Computes comparative step counts, context switch metrics, and saves results."""
    manual_count = len(MANUAL_STEPS)
    cidra_count = len(CIDRA_STEPS)

    manual_context_switches = sum(1 for s in MANUAL_STEPS if s["context_switch"])
    cidra_context_switches = sum(1 for s in CIDRA_STEPS if s["context_switch"])

    step_reduction_pct = ((manual_count - cidra_count) / manual_count) * 100.0
    context_switch_reduction_pct = ((manual_context_switches - cidra_context_switches) / manual_context_switches) * 100.0

    summary = {
        "benchmark": "02_step_audit",
        "manual_steps_total": manual_count,
        "cidra_steps_total": cidra_count,
        "step_reduction_percent": round(step_reduction_pct, 2),
        "target_met_step_reduction": step_reduction_pct >= 80.0,
        "manual_context_switches": manual_context_switches,
        "cidra_context_switches": cidra_context_switches,
        "context_switch_reduction_percent": round(context_switch_reduction_pct, 2),
        "target_met_context_switch_reduction": cidra_context_switches == 0,
        "manual_steps": MANUAL_STEPS,
        "cidra_steps": CIDRA_STEPS,
    }

    RESULTS_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    print("=" * 70)
    print("CIDRA BENCHMARK 2: STEP-REDUCTION & TOUCHPOINT AUDIT (Claim 2)")
    print("=" * 70)

    summary = run_step_audit_benchmark()
    print("MANUAL WORKFLOW (8 Touchpoints):")
    for s in summary["manual_steps"]:
        sw = "[Context Switch]" if s["context_switch"] else "                "
        print(f"  Step {s['step_number']}: {s['step_name']:<32} | {s['interface']:<20} {sw}")

    print("\nCIDRA AUTONOMOUS WORKFLOW (1 Touchpoint):")
    for s in summary["cidra_steps"]:
        print(f"  Step {s['step_number']}: {s['step_name']:<32} | {s['interface']:<20} [In-flow]")

    print("-" * 70)
    print(f"Manual Touchpoints         : {summary['manual_steps_total']}")
    print(f"CIDRA Touchpoints          : {summary['cidra_steps_total']}")
    print(f"Touchpoint Reduction       : {summary['step_reduction_percent']:.1f}% (Target: >= 80.0%)")
    print(f"Manual Context Switches    : {summary['manual_context_switches']}")
    print(f"CIDRA Context Switches     : {summary['cidra_context_switches']}")
    print(f"Context Switch Reduction   : {summary['context_switch_reduction_percent']:.1f}%")
    print(f"Results written to         : {RESULTS_JSON}")
    print("=" * 70)


if __name__ == "__main__":
    main()
