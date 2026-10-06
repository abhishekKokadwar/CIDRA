"""Measured results: run the fixture corpus and report three numbers.

  1. Does it fix things?   diagnosis accuracy, verified-fix rate, correct declines
  2. Does it ever lie?     false-verified rate, by a held-out check per fix
  3. What does it cost?    wall-clock time, requests, tokens and dollars per run

Every figure comes from a real run record: the CI log is fetched from GitHub,
the failure is reproduced in the Docker sandbox and the patch is audited,
applied and verified there. Nothing is a constant. Publishing is a dry run.

The held-out check is what separates "CIDRA says verified" from "actually
fixed". For each verified fix, CIDRA's diff is applied to the failing commit in
a fresh sandbox and judged by tests the model never saw: the test suite from the
known-good reference branch, plus any eval/fixtures/<id>/held_out/test_*.py.

    # with the model configured in the environment (CIDRA_BASE_URL, CIDRA_API_KEY, ...)
    python eval/measure.py --label my-model --price-in 1 --price-out 5
    # with the scripted stub model: checks the harness itself, costs nothing
    python eval/measure.py --stub
    # a subset
    python eval/measure.py --stub F-02b F-04
    # proof that the held-out check has teeth: a scripted patch that special-cases
    # the one visible test is verified by the pipeline and caught here
    python eval/measure.py --stub --stub-answers cheat_llm.json --out cheat.json F-02b

Needs Docker, a clone of the practice repo (CIDRA_PRACTICE_REPO) and a GitHub
token that can read its Actions logs (CIDRA_GITHUB_TOKEN_RO).
"""

import argparse
import io
import json
import os
import pathlib
import statistics
import subprocess
import sys
import tarfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "eval" / "fixtures"
RESULTS = ROOT / "eval" / "results"
STUB_PORT = 8765


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure CIDRA on the fixture corpus.")
    parser.add_argument("fixtures", nargs="*", help="fixture ids (default: all)")
    parser.add_argument("--stub", action="store_true", help="use the scripted stub model")
    parser.add_argument("--stub-answers", default="fake_llm.json",
                        help="answers file inside each fixture folder (default: fake_llm.json)")
    parser.add_argument("--label", help="name for this run's model in the results (default: the model id)")
    parser.add_argument("--price-in", type=float, default=0.0, help="$ per million prompt tokens")
    parser.add_argument("--price-out", type=float, default=0.0, help="$ per million completion tokens")
    parser.add_argument("--out", help="results JSON path (default: eval/results/<label>.json)")
    return parser.parse_args()


ARGS = _args()

# Set before cidra.config is imported. The fallback providers are switched off so
# the numbers describe exactly one model.
os.environ.update({"OPENROUTER_API_KEY_2": "", "GROQ_API_KEY": "", "NVIDIA_API_KEY_KIMI": "", "NVIDIA_API_KEY_GLM": ""})
os.environ["CIDRA_FIX_CACHE"] = str(ROOT / "worktrees" / "measure_fix_cache.json")  # never the real cache
os.environ.pop("GITHUB_STEP_SUMMARY", None)
if ARGS.stub:
    os.environ.update({"CIDRA_BASE_URL": f"http://127.0.0.1:{STUB_PORT}/v1", "CIDRA_API_KEY": "fake",
                       "CIDRA_MODEL_ANALYZE": "stub", "CIDRA_MODEL_FIX": "stub"})

from cidra import config  # noqa: E402
from cidra.graph import build_graph  # noqa: E402
from cidra.integrations import llm  # noqa: E402
from cidra.nodes.checkout import prepare_checkout, remove_checkout  # noqa: E402
from cidra.nodes.environment import env_prefix  # noqa: E402
from cidra.sandbox import limits  # noqa: E402
from cidra.sandbox.runner import Session  # noqa: E402


def _held_out_tar(practice: str, reference_ref: str, fid: str) -> bytes:
    """The reference branch's tests/ plus this fixture's extra held-out tests."""
    reference = subprocess.check_output(["git", "-C", practice, "archive", reference_ref, "tests"])
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as out:
        with tarfile.open(fileobj=io.BytesIO(reference)) as src:
            for member in src.getmembers():
                out.addfile(member, src.extractfile(member) if member.isfile() else None)
        for path in sorted((FIXTURES / fid / "held_out").glob("test_*.py")):
            data = path.read_bytes()
            info = tarfile.TarInfo(f"tests/test_heldout_{path.name.removeprefix('test_')}")
            info.size = len(data)
            out.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def held_out_check(practice: str, sha: str, diff: str, fid: str, reference_ref: str, ci_env: dict) -> dict:
    """Judge CIDRA's diff by tests it never saw. Returns {"passed": bool, "detail": str}."""
    run_id = f"heldout-{fid}"
    try:
        tree = prepare_checkout(run_id, practice, sha)
        with Session(tree) as session:
            applied = session.apply_patch(diff)
            if not applied.passed:
                return {"passed": False, "detail": "the verified diff did not apply to a clean checkout"}
            session.container.put_archive(limits.WORKDIR, _held_out_tar(practice, reference_ref, fid))
            installed = session.install("pip install --quiet -r requirements.txt")
            if not installed.passed:
                return {"passed": False, "detail": "dependency install failed after the fix"}
            result = session.run("verify", env_prefix({"ci_env": ci_env}) + config.TEST_COMMAND)
        tail = (result.stdout_tail or "").strip().splitlines()[-1:] or [""]
        return {"passed": result.passed, "detail": tail[0][:160]}
    finally:
        remove_checkout(run_id)


def run_fixture(fid: str) -> dict:
    folder = FIXTURES / fid
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    practice = config.PRACTICE_REPO_DIR
    reference_ref = meta.get("reference_ref", "origin/main")
    sha = subprocess.check_output(
        ["git", "-C", practice, "rev-parse", f"origin/{meta['gh_branch']}"], text=True).strip()
    pathlib.Path(os.environ["CIDRA_FIX_CACHE"]).unlink(missing_ok=True)

    server = None
    if ARGS.stub:
        from scripts.fake_llm import serve
        server = serve(str(folder / ARGS.stub_answers), STUB_PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.time()
    try:
        llm.clear_latest_telemetry()
        state = build_graph().invoke({
            "run_id": str(meta["gh_run_id"]), "repo": meta["gh_repo"], "commit_sha": sha,
            "source_dir": practice, "dry_run": True,
        })
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    seconds = round(time.time() - started, 1)
    usage = llm.usage_summary()

    analysis = state.get("analysis")
    outcome = state.get("outcome")
    verified = bool(state.get("verified"))
    record = {
        "fixture": fid,
        "failure_class": meta.get("class"),
        "expected_outcome": expected["expected_outcome"],
        "outcome": outcome,
        "outcome_matches": outcome == expected["expected_outcome"],
        "expected_category": expected["expected_analysis"]["category"],
        "category": analysis.category if analysis else None,
        "diagnosis_correct": bool(analysis) and analysis.category == expected["expected_analysis"]["category"],
        "reproduced": state.get("reproduced"),
        "verified": verified,
        "fix_attempts": state.get("fix_attempts", 0),
        "held_out": None,
        "seconds": seconds,
        "requests": usage["requests"],
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "cost_usd": round(usage["prompt_tokens"] / 1e6 * ARGS.price_in
                          + usage["completion_tokens"] / 1e6 * ARGS.price_out, 5),
        "error": state.get("analysis_error"),
        "diff": state.get("fix_diff") if verified else None,
    }
    if verified and state.get("fix_diff"):
        record["held_out"] = held_out_check(practice, sha, state["fix_diff"], fid, reference_ref,
                                            state.get("ci_env") or {})
    return record


def _rate(hits: int, total: int) -> str:
    return f"{hits}/{total}" + (f" ({100 * hits / total:.0f}%)" if total else "")


def summarize(records: list[dict]) -> dict:
    fixable = [r for r in records if r["expected_outcome"] == "verified_fix"]
    declinable = [r for r in records if r["expected_outcome"] != "verified_fix"]
    verified = [r for r in records if r["verified"]]
    false_verified = [r for r in verified if not (r["held_out"] or {}).get("passed")]
    return {
        "runs": len(records),
        "diagnosis_correct": _rate(sum(r["diagnosis_correct"] for r in records), len(records)),
        "verified_fix_rate": _rate(sum(r["verified"] for r in fixable), len(fixable)),
        "correct_declines": _rate(sum(r["outcome_matches"] and not r["verified"] for r in declinable), len(declinable)),
        "verified_claims": len(verified),
        "false_verified": _rate(len(false_verified), len(verified)),
        "false_verified_fixtures": [r["fixture"] for r in false_verified],
        "median_seconds": statistics.median(r["seconds"] for r in records) if records else None,
        "median_requests": statistics.median(r["requests"] for r in records) if records else None,
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in records),
        "total_completion_tokens": sum(r["completion_tokens"] for r in records),
        "total_cost_usd": round(sum(r["cost_usd"] for r in records), 4),
        "median_cost_usd": round(statistics.median(r["cost_usd"] for r in records), 4) if records else None,
    }


def _preflight() -> str | None:
    """Why the run cannot start, or None. Checked before any model call is made."""
    try:
        from cidra.sandbox.runner import client
        client().ping()
    except Exception as e:  # noqa: BLE001
        return f"Docker is not reachable: {str(e)[:120]}"
    if not (pathlib.Path(config.PRACTICE_REPO_DIR) / ".git").exists():
        return f"practice repo not found at {config.PRACTICE_REPO_DIR} (set CIDRA_PRACTICE_REPO)"
    return None


def main() -> int:
    problem = _preflight()
    if problem:
        print(f"not started: {problem}", file=sys.stderr)
        return 2
    wanted = ARGS.fixtures or sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    label = ARGS.label or ("stub" if ARGS.stub else config.MODEL_FIX)
    print(f"model: {label} | endpoint: {config.BASE_URL} | fixtures: {len(wanted)}", flush=True)

    records = []
    for fid in wanted:
        r = run_fixture(fid)
        records.append(r)
        held = "-" if r["held_out"] is None else ("pass" if r["held_out"]["passed"] else "FAIL")
        print(f"{fid:<6} outcome={r['outcome']:<15} expected={r['expected_outcome']:<15} "
              f"diagnosis={'ok' if r['diagnosis_correct'] else 'WRONG':<5} held_out={held:<4} "
              f"{r['seconds']:>5}s {r['requests']} req {r['prompt_tokens']}+{r['completion_tokens']} tok "
              f"${r['cost_usd']:.4f}", flush=True)

    summary = summarize(records)
    result = {
        "model": label,
        "endpoint": config.BASE_URL,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "price_per_mtok": {"prompt": ARGS.price_in, "completion": ARGS.price_out},
        "summary": summary,
        "runs": records,
    }
    out = pathlib.Path(ARGS.out) if ARGS.out else RESULTS / f"{label.replace('/', '_').replace(':', '_')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("\n1. Does it fix things?")
    print(f"   diagnosis correct   {summary['diagnosis_correct']}")
    print(f"   verified fixes      {summary['verified_fix_rate']} of the fixable cases")
    print(f"   correct declines    {summary['correct_declines']} of the cases it should not patch")
    print("2. Does it ever lie?")
    print(f"   false verified      {summary['false_verified']} of its verified claims failed the held-out check")
    print("3. What does it cost?")
    print(f"   median per run      {summary['median_seconds']}s, {summary['median_requests']} requests, "
          f"${summary['median_cost_usd']}")
    print(f"   total               {summary['total_prompt_tokens']} prompt + "
          f"{summary['total_completion_tokens']} completion tokens, ${summary['total_cost_usd']}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
