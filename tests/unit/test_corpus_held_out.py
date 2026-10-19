"""Every BugsInPy case CIDRA claims to fix has its own held-out tests, a command
that runs them, and a judgement on file that the README's number comes from
(ROADMAP M3). Running the sets needs the corpus clones and Python 3.7 images:
`python eval/measure.py --corpus eval/corpus --validate` and `--rejudge`."""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results"
pytestmark = pytest.mark.req("M3-HELDOUT")


def test_each_fixed_case_has_held_out_tests_that_its_command_runs():
    runs = json.loads((RESULTS / "claude-haiku-4-5-bugsinpy-v4.json").read_text(encoding="utf-8"))["runs"]
    fixed = [r["fixture"] for r in runs if r["outcome"] == "verified_fix"]
    assert len(fixed) == 5
    for fid in fixed:
        folder = ROOT / "eval" / "corpus" / fid
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        tests = sorted((folder / "held_out").glob("test_*.py"))
        assert tests, fid
        held_dir = pathlib.PurePosixPath(meta["held_out_paths"][0]).parent
        for t in tests:  # measure.py drops each one in as test_heldout_<name>.py
            assert f"{held_dir}/test_heldout_{t.name.removeprefix('test_')}" in meta["held_out_command"], (fid, t.name)


def test_the_published_judgement_covers_every_fixed_case_and_finds_no_false_verified():
    judged = json.loads((RESULTS / "claude-haiku-4-5-bugsinpy-v4-held-out.json").read_text(encoding="utf-8"))
    assert judged["false_verified"] == "0/5"
    assert all(r["verdict"] == "genuine" and r["held_out_unseen_failures"] for r in judged["runs"])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "| 0 / 5 ([judged](eval/results/claude-haiku-4-5-bugsinpy-v4-held-out.json)" in readme
