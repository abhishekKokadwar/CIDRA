"""CI's requirements check: every requirement has passing evidence in this run.

    python scripts/check_requirements.py docs/requirements.yml req-unit.json req-integration.json \\
        --jobs '{"pipeline": "success", "sandbox": "success"}'

A requirement holds when a test tagged with its id passed (a skipped test does not
count) and every CI job it lists succeeded. Exit 1, with the reason, when one does
not hold or a test names an id the file does not define. The table goes to stdout
and, in CI, to the job summary.
"""

import argparse
import json
import os
import re
import sys

import yaml


def check(requirements: list[dict], results: dict[str, dict], jobs: dict[str, str]) -> tuple[list[str], list[str]]:
    """(table rows, problems). Pure: the CLI below does the reading and writing."""
    known = {r["id"] for r in requirements}
    problems = [f"{node} is tagged with unknown requirement {rid}"
                for node, r in sorted(results.items()) for rid in r["req"] if rid not in known]
    rows = []
    for req in requirements:
        tests = {node: r["outcome"] for node, r in results.items() if req["id"] in r["req"]}
        passed = [n for n, o in tests.items() if o == "passed"]
        needed = req.get("jobs") or []
        jobs_ok = all(jobs.get(j) == "success" for j in needed)
        ok = jobs_ok and (bool(passed) or bool(needed))
        if not passed and not needed:
            problems.append(f"{req['id']}: no passing test ({len(tests)} tagged, "
                            f"{sum(o == 'skipped' for o in tests.values())} skipped)")
        for j in needed:
            if jobs.get(j) != "success":
                problems.append(f"{req['id']}: CI job '{j}' did not pass ({jobs.get(j, 'not run')})")
        failed = sorted(n for n, o in tests.items() if o == "failed")
        problems += [f"{req['id']}: {n} failed" for n in failed]
        ok = ok and not failed
        evidence = f"{len(passed)} passed" + (f", jobs: {', '.join(needed)}" if needed else "")
        rows.append(f"| {'pass' if ok else 'FAIL'} | {req['id']} | {req['title']} | {evidence} |")
    return rows, problems


def from_vitest(report: dict) -> dict[str, dict]:
    """A vitest JSON report in the shape conftest.py writes. The dashboard's
    tests name their requirements in the title, e.g. "[UI-KEYS] counts ..."."""
    return {f"{f['name']}::{t['fullName']}": {"req": re.findall(r"\[([A-Z0-9-]+)\]", t["fullName"]),
                                             "outcome": t["status"] if t["status"] in ("passed", "failed") else "skipped"}
            for f in report["testResults"] for t in f["assertionResults"]}


def from_playwright(report: dict) -> dict[str, dict]:
    """A Playwright JSON report in the same shape: a spec's [ID]s in its title, and it
    passed only if every run of it was as expected."""
    out: dict[str, dict] = {}

    def walk(suite: dict, where: str) -> None:
        for spec in suite.get("specs", []):
            statuses = {t["status"] for t in spec["tests"]}
            outcome = "skipped" if statuses == {"skipped"} else "passed" if statuses == {"expected"} else "failed"
            out[f"{where}::{spec['title']}"] = {"req": re.findall(r"\[([A-Z0-9-]+)\]", spec["title"]), "outcome": outcome}
        for child in suite.get("suites", []):
            walk(child, f"{where}::{child['title']}")

    for suite in report["suites"]:
        walk(suite, suite["title"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("requirements")
    ap.add_argument("reports", nargs="*", help="JSON files written with CIDRA_REQ_REPORT, or vitest / Playwright JSON reports")
    ap.add_argument("--jobs", default="{}", help="JSON object: CI job name -> result")
    args = ap.parse_args()
    with open(args.requirements, encoding="utf-8") as f:
        requirements = yaml.safe_load(f)
    results: dict[str, dict] = {}
    for path in args.reports:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
        if "testResults" in report:
            report = from_vitest(report)
        elif "suites" in report and "config" in report:
            report = from_playwright(report)
        results.update(report)
    rows, problems = check(requirements, results, json.loads(args.jobs))
    out = "\n".join(["## Requirements", "", "| | Id | Requirement | Evidence |", "|---|---|---|---|", *rows])
    if problems:
        out += "\n\n**Not proven:**\n\n" + "\n".join(f"- {p}" for p in problems)
    print(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(out + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
