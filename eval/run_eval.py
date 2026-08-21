"""Fixture eval harness. See docs/5_fixtures.md §6.

Tier 1 (default) is free and instant: pure isolation, no LLM, no Docker.
Tier 2 adds the analyze call. Tier 3 needs Docker and arrives in Phase 5.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from cidra.nodes.ingest import isolate_error  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(fid: pathlib.Path):
    exp = json.loads((fid / "expected.json").read_text())
    # raw.log is real CI output (Phase 1 capture); local.log is the offline stand-in.
    for name in ("raw.log", "local.log"):
        p = fid / name
        if p.exists():
            return exp, p.read_text(encoding="utf-8", errors="replace"), name
    return exp, None, None


def tier1(fid: pathlib.Path) -> dict:
    exp, log, src = load(fid)
    if log is None:
        return {"fixture": fid.name, "status": "NOLOG"}
    out = isolate_error({"raw_log": log})
    region = out["error_region"]
    missing = [s for s in exp["must_contain_in_error_region"] if s not in region]
    return {
        "fixture": fid.name,
        "status": "PASS" if not missing else "FAIL",
        "source": src,
        "missing": missing,
        "markers": out["log_markers"],
        "region_lines": region.count("\n") + 1,
    }


def tier2(fid: pathlib.Path) -> dict:
    from cidra.config import MODEL_ANALYZE
    from cidra.nodes.analyze import analyze_region

    exp, log, _ = load(fid)
    if log is None:
        return {"fixture": fid.name, "status": "NOLOG"}
    region = isolate_error({"raw_log": log})["error_region"]
    got = analyze_region(region)
    want = exp["expected_analysis"]
    fields = {}
    for field in exp["scoring"]:
        fields[field] = (getattr(got, field, None), want.get(field))
    ok = all(a == b for a, b in fields.values())
    return {
        "fixture": fid.name,
        "status": "PASS" if ok else "FAIL",
        "model": MODEL_ANALYZE,
        "fields": {k: {"got": a, "want": b} for k, (a, b) in fields.items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, default=1, choices=[1, 2])
    ap.add_argument("--only", help="fixture id, e.g. F-01")
    args = ap.parse_args()

    run = tier1 if args.tier == 1 else tier2
    dirs = sorted(d for d in FIXTURES.iterdir() if d.is_dir())
    if args.only:
        dirs = [d for d in dirs if d.name == args.only]

    rows = [run(d) for d in dirs]
    for r in rows:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "NOLOG": "skip"}[r["status"]]
        extra = ""
        if r["status"] == "FAIL":
            extra = f"  missing={r.get('missing')}" if args.tier == 1 else f"  {r.get('fields')}"
        print(f"{mark} {r['fixture']:<7}{extra}")

    failed = sum(r["status"] == "FAIL" for r in rows)
    scored = sum(r["status"] != "NOLOG" for r in rows)
    print(f"\ntier {args.tier}: {scored - failed}/{scored} pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
