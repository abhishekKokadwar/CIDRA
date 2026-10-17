"""Records which requirement each test proves, for CI's requirements check.

A test tagged @pytest.mark.req("R7") is evidence for R7 in docs/requirements.yml.
With CIDRA_REQ_REPORT set, the run writes {nodeid: {"req": [...], "outcome": ...}}
there; scripts/check_requirements.py reads it. Unset, nothing is written.
"""

import json
import os

import pytest

_RESULTS: dict[str, dict] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    ids = [i for mark in item.iter_markers("req") for i in mark.args]
    if not ids or (report.when != "call" and report.passed):
        return
    outcome = "passed" if report.passed else "skipped" if report.skipped else "failed"
    # A failure or skip in any phase (setup, call, teardown) is what counts.
    if _RESULTS.get(item.nodeid, {}).get("outcome", "passed") == "passed":
        _RESULTS[item.nodeid] = {"req": ids, "outcome": outcome}


def pytest_sessionfinish(session):
    path = os.environ.get("CIDRA_REQ_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_RESULTS, f, indent=1)
