"""CI's requirements check: green must mean every requirement has passing evidence."""

import pathlib

import yaml

from scripts.check_requirements import check

REQS = [{"id": "R1", "title": "Auth"}, {"id": "R2", "title": "Sandbox"},
        {"id": "E2E", "title": "Pipeline", "jobs": ["pipeline"]}]


def _problems(results, jobs=None):
    return check(REQS, results, {"pipeline": "success"} if jobs is None else jobs)[1]


def test_every_requirement_with_a_passing_test_holds():
    assert _problems({"t::a": {"req": ["R1"], "outcome": "passed"},
                      "t::b": {"req": ["R2"], "outcome": "passed"}}) == []


def test_a_requirement_whose_tests_were_skipped_is_not_proven():
    problems = _problems({"t::a": {"req": ["R1"], "outcome": "passed"},
                          "t::b": {"req": ["R2"], "outcome": "skipped"}})
    assert problems == ["R2: no passing test (1 tagged, 1 skipped)"]


def test_a_requirement_with_no_tests_at_all_is_not_proven():
    assert _problems({"t::a": {"req": ["R1"], "outcome": "passed"}}) == ["R2: no passing test (0 tagged, 0 skipped)"]


def test_a_failed_tagged_test_is_reported_even_beside_a_passing_one():
    problems = _problems({"t::a": {"req": ["R1"], "outcome": "passed"}, "t::c": {"req": ["R1"], "outcome": "failed"},
                          "t::b": {"req": ["R2"], "outcome": "passed"}})
    assert problems == ["R1: t::c failed"]


def test_job_evidence_must_have_passed():
    ok = {"t::a": {"req": ["R1"], "outcome": "passed"}, "t::b": {"req": ["R2"], "outcome": "passed"}}
    assert _problems(ok, {"pipeline": "success"}) == []
    assert _problems(ok, {"pipeline": "skipped"}) == ["E2E: CI job 'pipeline' did not pass (skipped)"]
    assert _problems(ok, {}) == ["E2E: CI job 'pipeline' did not pass (not run)"]


def test_a_tag_naming_an_unknown_requirement_fails():
    problems = _problems({"t::a": {"req": ["R1", "R9"], "outcome": "passed"},
                          "t::b": {"req": ["R2"], "outcome": "passed"}})
    assert problems == ["t::a is tagged with unknown requirement R9"]


def test_the_projects_requirements_file_is_well_formed():
    reqs = yaml.safe_load((pathlib.Path(__file__).resolve().parents[2] / "docs" / "requirements.yml").read_text(encoding="utf-8"))
    ids = [r["id"] for r in reqs]
    assert len(ids) == len(set(ids)) and {"R1", "R8"} <= set(ids)
    assert all(r.get("title") and r.get("accept") for r in reqs)
