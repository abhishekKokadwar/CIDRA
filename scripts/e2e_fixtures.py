"""Run every practice fixture through the whole pipeline with the stub LLM.

No API key and no cost: the model's answers are scripted per fixture
(eval/fixtures/<id>/fake_llm.json). Everything else is real: the CI log is
fetched from GitHub, the failure is reproduced in the Docker sandbox, the patch
is audited, applied and verified. Publishing is a dry run.

Needs Docker, a clone of the practice repo (CIDRA_PRACTICE_REPO) and a GitHub
token that can read its Actions logs (CIDRA_GITHUB_TOKEN_RO).

    python scripts/e2e_fixtures.py            # all fixtures
    python scripts/e2e_fixtures.py F-02b F-04 # some
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PORT = 8765

# Set before cidra.config is imported: the stub is the only model in the chain.
os.environ.update({
    "CIDRA_BASE_URL": f"http://127.0.0.1:{PORT}/v1", "CIDRA_API_KEY": "fake",
    "CIDRA_MODEL_ANALYZE": "fake", "CIDRA_MODEL_FIX": "fake",
    "OPENROUTER_API_KEY_2": "", "GROQ_API_KEY": "", "NVIDIA_API_KEY_KIMI": "", "NVIDIA_API_KEY_GLM": "",
    "CIDRA_FIX_CACHE": str(ROOT / "worktrees" / "e2e_fix_cache.json"),  # never the real cache
})
os.environ.pop("GITHUB_STEP_SUMMARY", None)

from cidra import config  # noqa: E402
from cidra.graph import build_graph  # noqa: E402
from cidra.integrations import llm  # noqa: E402
from scripts.fake_llm import serve  # noqa: E402

FIXTURES = ROOT / "eval" / "fixtures"


def run_fixture(fid: str) -> tuple[bool, str]:
    folder = FIXTURES / fid
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))["expected_outcome"]
    answers = folder / "fake_llm.json"
    if not answers.exists():
        return False, "no fake_llm.json"

    practice = config.PRACTICE_REPO_DIR
    sha = subprocess.check_output(
        ["git", "-C", practice, "rev-parse", f"origin/{meta['gh_branch']}"], text=True).strip()
    pathlib.Path(os.environ["CIDRA_FIX_CACHE"]).unlink(missing_ok=True)

    server = serve(str(answers), PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.time()
    try:
        llm.clear_latest_telemetry()
        state = build_graph().invoke({
            "run_id": str(meta["gh_run_id"]), "repo": meta["gh_repo"], "commit_sha": sha,
            "source_dir": practice, "dry_run": True,
        })
    finally:
        server.shutdown()
        server.server_close()

    outcome = state.get("outcome")
    detail = (f"outcome={outcome} expected={expected} reproduced={state.get('reproduced')} "
              f"verified={state.get('verified')} fix_attempts={state.get('fix_attempts', 0)} "
              f"llm_requests={llm.usage_summary()['requests']} {time.time() - started:.0f}s")
    if state.get("analysis_error"):
        detail += f" error={state['analysis_error'][:120]!r}"
    return outcome == expected, detail


if __name__ == "__main__":
    wanted = sys.argv[1:] or sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    failures = 0
    for fid in wanted:
        ok, detail = run_fixture(fid)
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} {fid:<6} {detail}", flush=True)
    print(f"\n{len(wanted) - failures}/{len(wanted)} fixtures reached their expected outcome")
    sys.exit(1 if failures else 0)
