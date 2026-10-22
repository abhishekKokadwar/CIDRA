"""The table of measured BugsInPy runs in reports/RESULTS.md, computed from the
result files in eval/results/. Every number in it comes from a committed file.

    python eval/results_table.py      # prints the table to paste into the report
"""

import json
import pathlib
import statistics

RESULTS = pathlib.Path(__file__).resolve().parent / "results"
RUNS = ["v2", "v3", "v4", "v5", "v6", "v7"]


def row(version: str) -> str:
    name = f"claude-haiku-4-5-bugsinpy-{version}"
    runs = json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))["runs"]
    fixable = [r for r in runs if r["expected_outcome"] == "verified_fix"]
    decline = [r for r in runs if r["expected_outcome"] == "diagnosis_only"]
    judged = RESULTS / f"{name}-held-out.json"
    false = (f"[{json.loads(judged.read_text(encoding='utf-8'))['false_verified'].replace('/', ' / ')}]"
             f"(../eval/results/{judged.name})") if judged.is_file() else "not judged"
    costs = [r["cost_usd"] or 0 for r in runs]
    return (f"| [{version}](../eval/results/{name}.json) | {len(runs)} "
            f"| {sum(bool(r['diagnosis_correct']) for r in runs)} / {len(runs)} "
            f"| {sum(r['outcome'] == 'verified_fix' for r in fixable)} / {len(fixable)} "
            f"| {sum(r['outcome'] == 'diagnosis_only' for r in decline)} / {len(decline)} "
            f"| {false} | ${sum(costs):.2f} | ${statistics.median(costs):.3f} |")


def table() -> str:
    head = ("| Run | Cases | Correct diagnosis | Verified fix (fixable cases) | Correctly declined "
            "| False \"verified\" (held-out judged) | Total cost | Median per case |\n"
            "|---|---|---|---|---|---|---|---|")
    return "\n".join([head, *map(row, RUNS)])


if __name__ == "__main__":
    print(table())
