"""Measured results: run a fixture corpus and report three numbers.

  1. Does it fix things?   diagnosis accuracy, verified-fix rate, correct declines
  2. Does it ever lie?     false-verified rate, by a held-out check per fix
  3. What does it cost?    wall-clock time, requests, tokens and dollars per run

Every figure comes from a real run record: the failure is reproduced in the
Docker sandbox and the patch is audited, applied and verified there. Nothing is
a constant. Publishing is a dry run.

The held-out check is what separates "CIDRA says verified" from "actually
fixed". For each verified fix, CIDRA's diff is applied to the failing commit in
a fresh sandbox and judged by tests the model never saw: the fix commit's tests,
plus any <fixture>/held_out/test_*.py. A held-out set only counts once it is
shown to pass on the fix commit and to catch something the failing run did not
already show: a test that fails on the buggy code and was not failing before,
or the fixture's deliberately wrong patch. Fixtures without such a set are left
out of the false-verified rate and listed.

    # with the model configured in the environment (CIDRA_BASE_URL, CIDRA_API_KEY, ...)
    python eval/measure.py --label my-model --price-in 1 --price-out 5
    # with the scripted stub model: checks the harness itself, costs nothing
    python eval/measure.py --stub
    # a subset, or another corpus folder
    python eval/measure.py --stub F-02b F-04
    python eval/measure.py --stub --corpus eval/corpus
    # check the held-out sets themselves, with no model call
    python eval/measure.py --validate
    # proof that the audit gate refuses a patch that special-cases the visible test
    python eval/measure.py --stub --stub-answers cheat_llm.json --out cheat.json F-02b

The fixture format is in eval/fixtures/README.md. Needs Docker. A fixture
without `repo_url` uses the practice repo clone (CIDRA_PRACTICE_REPO); one
without a stored log needs a GitHub token to fetch it (CIDRA_GITHUB_TOKEN_RO).
"""

import argparse
import io
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import tarfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "eval" / "results"
STUB_PORT = 8765


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure CIDRA on a fixture corpus.")
    parser.add_argument("fixtures", nargs="*", help="fixture ids (default: all)")
    parser.add_argument("--corpus", default=str(ROOT / "eval" / "fixtures"),
                        help="folder holding one sub-folder per fixture (default: eval/fixtures)")
    parser.add_argument("--stub", action="store_true", help="use the scripted stub model")
    parser.add_argument("--stub-answers", default="fake_llm.json",
                        help="answers file inside each fixture folder (default: fake_llm.json)")
    parser.add_argument("--label", help="name for this run's model in the results (default: the model id)")
    parser.add_argument("--price-in", type=float, default=0.0, help="$ per million prompt tokens")
    parser.add_argument("--price-out", type=float, default=0.0, help="$ per million completion tokens")
    parser.add_argument("--validate", action="store_true",
                        help="check the held-out sets themselves (no model call): each must pass on the "
                             "fix commit, catch the fixture's cheat_llm.json patch if it has one, and "
                             "add a failing test on the failing commit or catch that patch")
    parser.add_argument("--out", help="results JSON path (default: eval/results/<label>.json)")
    return parser.parse_args()


ARGS = _args()
FIXTURES = pathlib.Path(ARGS.corpus).resolve()

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
from cidra.nodes.environment import (  # noqa: E402
    sandbox_install_command, sandbox_test_command, workflow_env, workflow_python)
from cidra.sandbox import limits  # noqa: E402
from cidra.sandbox.runner import Session  # noqa: E402

# Per-fixture overrides the pipeline takes as run input.
_RUN_OVERRIDES = ("install_command", "test_command", "python_version")
# pytest's short summary: "FAILED tests/test_x.py::test_y - ..." / "ERROR tests/test_x.py"
_FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)


def _git(repo: str, *args: str) -> str:
    return subprocess.check_output(["git", "-C", repo, *args], text=True, stderr=subprocess.DEVNULL).strip()


def _corpus_clone(url: str) -> str:
    """A local clone of a fixture's repository, made once and reused."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://")[-1].removesuffix(".git")).strip("_")
    dest = pathlib.Path(config.WORKTREE_ROOT).resolve() / "corpus" / name
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", "--quiet", url, str(dest)])
    return str(dest)


def _commit(repo: str, ref: str, pin: bool) -> str:
    """Resolve `ref` in the clone, fetching it if it is not there yet.

    `pin` tags the commit: the pipeline clones this clone, and a commit that no
    branch or tag reaches (a pull request head, a deleted branch) would not come along.
    """
    try:
        sha = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        _git(repo, "fetch", "--quiet", "origin", ref)
        sha = _git(repo, "rev-parse", "--verify", "FETCH_HEAD^{commit}")
    if pin:
        _git(repo, "tag", "--force", f"cidra-pin-{sha[:12]}", sha)
    return sha


def load_fixture(fid: str) -> dict:
    """One fixture, with its repository on disk and both commits resolved."""
    folder = FIXTURES / fid
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    url = meta.get("repo_url")
    repo = _corpus_clone(url) if url else config.PRACTICE_REPO_DIR
    log = folder / meta.get("log", "raw.log")
    held_out_paths = meta.get("held_out_paths") or ["tests"]
    first = pathlib.PurePosixPath(held_out_paths[0])
    return {
        "id": fid,
        "folder": folder,
        "meta": meta,
        "expected": json.loads((folder / "expected.json").read_text(encoding="utf-8")),
        "repo": repo,
        "failing_sha": _commit(repo, meta.get("failing_ref") or f"origin/{meta['gh_branch']}", pin=bool(url)),
        "fix_sha": _commit(repo, meta.get("fix_ref") or "origin/main", pin=bool(url)),
        "log": log.read_text(encoding="utf-8", errors="replace") if log.is_file() else None,
        "held_out_paths": held_out_paths,
        # where the fixture's own extra held-out files are dropped
        "held_out_dir": str(first.parent if first.suffix == ".py" else first),
        "overrides": {k: meta[k] for k in _RUN_OVERRIDES if meta.get(k)},
    }


def _held_out_tar(fx: dict) -> bytes:
    """The fix commit's test files plus this fixture's extra held-out tests."""
    reference = subprocess.check_output(
        ["git", "-C", fx["repo"], "archive", fx["fix_sha"], "--", *fx["held_out_paths"]])
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as out:
        with tarfile.open(fileobj=io.BytesIO(reference)) as src:
            for member in src.getmembers():
                out.addfile(member, src.extractfile(member) if member.isfile() else None)
        for path in sorted((fx["folder"] / "held_out").glob("test_*.py")):
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{fx['held_out_dir']}/test_heldout_{path.name.removeprefix('test_')}")
            info.size = len(data)
            out.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def held_out_check(fx: dict, sha: str, diff: str | None, ci_env: dict | None = None,
                   overlay: bool = True) -> dict:
    """Judge a diff (or the bare commit) by tests the model never saw.

    Returns {"passed": bool, "detail": str}. When the tests ran, "ran" is set and
    "failed" lists the test ids pytest reported. `overlay=False` leaves the
    held-out tests out, which gives the commit's own result to compare against.
    """
    run_id = f"heldout-{fx['id']}"
    try:
        tree = prepare_checkout(run_id, fx["repo"], sha)
        with Session(tree, fx["overrides"].get("python_version") or workflow_python(tree)) as session:
            state = {**fx["overrides"], "ci_env": workflow_env(tree) if ci_env is None else ci_env}
            if diff and not session.apply_patch(diff).passed:
                return {"passed": False, "detail": "the diff did not apply to a clean checkout"}
            if overlay:
                session.container.put_archive(limits.WORKDIR, _held_out_tar(fx))
            if not session.install(sandbox_install_command(state)).passed:
                return {"passed": False, "detail": "dependency install failed"}
            result = session.run("verify", sandbox_test_command(state))
        tail = (result.stdout_tail or "").strip().splitlines()[-1:] or [""]
        return {"passed": result.passed, "detail": tail[0][:160], "ran": True,
                "failed": sorted(set(_FAILED_TEST.findall(result.stdout_tail or "")))}
    finally:
        remove_checkout(run_id)


def validate_held_out(fx: dict) -> dict:
    """Is this fixture's held-out set fit to judge a fix?

    It must pass on the fix commit, and it must show something the failing run
    did not: a test that fails on the failing commit only once the held-out
    tests are added, or the fixture's deliberately wrong patch being caught.
    Tests the failing run already showed prove nothing here, because a patch
    can be written to satisfy exactly those. A wrong patch, when the fixture
    has one, must always be caught.
    """
    # ponytail: re-checked on every run (three or four sandbox runs per fixture),
    # and unseen failures are read from pytest's short summary only. Cache by
    # commit and held-out content if a large corpus makes this slow.
    reference = held_out_check(fx, fx["fix_sha"], None)
    before = held_out_check(fx, fx["failing_sha"], None, overlay=False)
    after = held_out_check(fx, fx["failing_sha"], None)
    unseen = sorted(set(after["failed"]) - set(before["failed"])) if before.get("ran") and after.get("ran") else []
    out = {"reference": reference, "unseen_failures": unseen, "cheat_caught": None}
    cheat_file = fx["folder"] / "cheat_llm.json"
    if cheat_file.exists():
        diff = json.loads(cheat_file.read_text(encoding="utf-8"))["Patch"]["diff"]
        cheat = held_out_check(fx, fx["failing_sha"], diff)
        out["cheat_caught"] = bool(cheat.get("ran")) and not cheat["passed"]
    out["valid"] = (reference["passed"] and out["cheat_caught"] is not False
                    and (bool(unseen) or bool(out["cheat_caught"])))
    return out


def run_fixture(fid: str) -> dict:
    fx = load_fixture(fid)
    meta, expected = fx["meta"], fx["expected"]
    pathlib.Path(os.environ["CIDRA_FIX_CACHE"]).unlink(missing_ok=True)

    run_input = {
        "run_id": str(meta.get("gh_run_id") or fid), "repo": meta.get("gh_repo") or f"corpus/{fid}",
        "commit_sha": fx["failing_sha"], "source_dir": fx["repo"], "dry_run": True, **fx["overrides"],
    }
    if fx["log"]:
        run_input["raw_log"] = fx["log"]  # stored with the fixture: no fetch, no token

    server = None
    if ARGS.stub:
        from scripts.fake_llm import serve
        server = serve(str(fx["folder"] / ARGS.stub_answers), STUB_PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.time()
    try:
        llm.clear_latest_telemetry()
        state = build_graph().invoke(run_input)
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
        "python_version": state.get("python_version"),
        "reproduced": state.get("reproduced"),
        "verified": verified,
        "fix_attempts": state.get("fix_attempts", 0),
        "held_out": None,
        "held_out_valid": None,
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
        record["held_out_valid"] = validate_held_out(fx)["valid"]
        record["held_out"] = held_out_check(fx, fx["failing_sha"], state["fix_diff"], state.get("ci_env") or {})
    return record


def _rate(hits: int, total: int) -> str:
    return f"{hits}/{total}" + (f" ({100 * hits / total:.0f}%)" if total else "")


def summarize(records: list[dict]) -> dict:
    fixable = [r for r in records if r["expected_outcome"] == "verified_fix"]
    declinable = [r for r in records if r["expected_outcome"] != "verified_fix"]
    verified = [r for r in records if r["verified"]]
    # Only a validated held-out set can say a verified claim was false.
    judged = [r for r in verified if r["held_out_valid"]]
    false_verified = [r for r in judged if not (r["held_out"] or {}).get("passed")]
    return {
        "runs": len(records),
        "diagnosis_correct": _rate(sum(r["diagnosis_correct"] for r in records), len(records)),
        "verified_fix_rate": _rate(sum(r["verified"] for r in fixable), len(fixable)),
        "correct_declines": _rate(sum(r["outcome_matches"] and not r["verified"] for r in declinable), len(declinable)),
        "verified_claims": len(verified),
        "false_verified": _rate(len(false_verified), len(judged)),
        "false_verified_fixtures": [r["fixture"] for r in false_verified],
        "false_verified_excluded": [r["fixture"] for r in verified if not r["held_out_valid"]],
        "median_seconds": statistics.median(r["seconds"] for r in records) if records else None,
        "median_requests": statistics.median(r["requests"] for r in records) if records else None,
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in records),
        "total_completion_tokens": sum(r["completion_tokens"] for r in records),
        "total_cost_usd": round(sum(r["cost_usd"] for r in records), 4),
        "median_cost_usd": round(statistics.median(r["cost_usd"] for r in records), 4) if records else None,
    }


def validate(wanted: list[str]) -> int:
    """Check the held-out set of every fixable fixture. No model call."""
    bad = 0
    for fid in wanted:
        fx = load_fixture(fid)
        if fx["expected"]["expected_outcome"] != "verified_fix":
            continue
        v = validate_held_out(fx)
        cheat = {None: "none", True: "caught", False: "NOT CAUGHT"}[v["cheat_caught"]]
        print(f"{fid:<6} fix_commit={'pass' if v['reference']['passed'] else 'FAIL'} "
              f"unseen_failures={len(v['unseen_failures'])} cheat={cheat}"
              + ("" if v["valid"] else f"  <-- not a valid held-out set ({v['reference']['detail']})"), flush=True)
        bad += not v["valid"]
    return 1 if bad else 0


def _preflight(wanted: list[str]) -> str | None:
    """Why the run cannot start, or None. Checked before any model call is made."""
    try:
        from cidra.sandbox.runner import client
        client().ping()
    except Exception as e:  # noqa: BLE001
        return f"Docker is not reachable: {str(e)[:120]}"
    metas = {}
    for fid in wanted:
        path = FIXTURES / fid / "meta.json"
        if not path.is_file():
            return f"no such fixture: {path}"
        metas[fid] = json.loads(path.read_text(encoding="utf-8"))
    if (any(not m.get("repo_url") for m in metas.values())
            and not (pathlib.Path(config.PRACTICE_REPO_DIR) / ".git").exists()):
        return f"practice repo not found at {config.PRACTICE_REPO_DIR} (set CIDRA_PRACTICE_REPO)"
    if ARGS.validate:
        return None
    no_log = [fid for fid, m in metas.items() if not (FIXTURES / fid / m.get("log", "raw.log")).is_file()]
    if no_log and not (os.environ.get("CIDRA_GITHUB_TOKEN_RO") or os.environ.get("CIDRA_GITHUB_TOKEN")):
        return f"no stored log for {', '.join(no_log)} and no GitHub token to fetch one (set CIDRA_GITHUB_TOKEN_RO)"
    return None


def main() -> int:
    wanted = ARGS.fixtures or sorted(p.name for p in FIXTURES.iterdir() if (p / "meta.json").is_file())
    problem = _preflight(wanted)
    if problem:
        print(f"not started: {problem}", file=sys.stderr)
        return 2
    if ARGS.validate:
        return validate(wanted)
    label = ARGS.label or ("stub" if ARGS.stub else config.MODEL_FIX)
    print(f"model: {label} | endpoint: {config.BASE_URL} | fixtures: {len(wanted)}", flush=True)

    records = []
    for fid in wanted:
        r = run_fixture(fid)
        records.append(r)
        held = "-" if r["held_out"] is None else ("pass" if r["held_out"]["passed"] else "FAIL")
        if r["held_out"] is not None and not r["held_out_valid"]:
            held += "*"
        print(f"{fid:<6} outcome={r['outcome']:<15} expected={r['expected_outcome']:<15} "
              f"diagnosis={'ok' if r['diagnosis_correct'] else 'WRONG':<5} held_out={held:<5} "
              f"{r['seconds']:>5}s {r['requests']} req {r['prompt_tokens']}+{r['completion_tokens']} tok "
              f"${r['cost_usd']:.4f}", flush=True)

    summary = summarize(records)
    result = {
        "model": label,
        "endpoint": config.BASE_URL,
        "corpus": FIXTURES.name,
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
    if summary["false_verified_excluded"]:
        print(f"   not judged          {', '.join(summary['false_verified_excluded'])}: "
              "verified, but no validated held-out set (marked *)")
    print("3. What does it cost?")
    print(f"   median per run      {summary['median_seconds']}s, {summary['median_requests']} requests, "
          f"${summary['median_cost_usd']}")
    print(f"   total               {summary['total_prompt_tokens']} prompt + "
          f"{summary['total_completion_tokens']} completion tokens, ${summary['total_cost_usd']}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
