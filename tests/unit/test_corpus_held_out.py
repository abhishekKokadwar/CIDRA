"""Every BugsInPy fix CIDRA claims in a published run is judged by its own
held-out tests, and the README's false-"verified" number is the judgement on
file (ROADMAP M3). Running the sets needs the corpus clones and the sandbox
images: `python eval/measure.py --corpus eval/corpus --rejudge <results>`."""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results"
pytestmark = pytest.mark.req("M3-HELDOUT")

# (run, judgement on file, false verified / judged)
PUBLISHED = [("claude-haiku-4-5-bugsinpy-v4", "0/5"), ("claude-haiku-4-5-bugsinpy-v6", "4/9")]


def _load(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("run, _", PUBLISHED)
def test_each_verified_fix_has_held_out_tests_that_its_command_runs(run, _):
    fixed = [r["fixture"] for r in _load(run)["runs"] if r["outcome"] == "verified_fix"]
    assert fixed
    for fid in fixed:
        folder = ROOT / "eval" / "corpus" / fid
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        tests = sorted((folder / "held_out").glob("test_*.py"))
        assert tests, fid
        held_dir = pathlib.PurePosixPath(meta["held_out_paths"][0]).parent
        for t in tests:  # measure.py drops each one in as test_heldout_<name>.py
            assert f"{held_dir}/test_heldout_{t.name.removeprefix('test_')}" in meta["held_out_command"], (fid, t.name)


@pytest.mark.parametrize("run, false_verified", PUBLISHED)
def test_the_judgement_covers_every_verified_fix_with_a_valid_set(run, false_verified):
    fixed = {r["fixture"] for r in _load(run)["runs"] if r["outcome"] == "verified_fix"}
    judged = _load(f"{run}-held-out")
    assert {r["fixture"] for r in judged["runs"]} == fixed
    assert all(r["verdict"] in ("genuine", "false_verified") and r["held_out_unseen_failures"] for r in judged["runs"])
    assert judged["false_verified"] == false_verified == \
        f"{sum(r['verdict'] == 'false_verified' for r in judged['runs'])}/{len(judged['runs'])}"


def test_the_readme_states_the_latest_judgement():
    run, false_verified = PUBLISHED[-1]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    shown = false_verified.replace("/", " / ")
    assert f"| **{shown}** ([judged](eval/results/{run}-held-out.json)" in readme
