"""Phase 2 checks. Offline: synthetic archives, no token, no network."""

import io
import zipfile

from cidra.integrations.github import _pick
from cidra.nodes.ingest import _clean, fetch_log, isolate_error

# A real GitHub log line: BOM on line 1, ISO timestamp on every line, ANSI in
# echoed commands, ##[group] folds around each step.
GH_LOG = "\n".join(
    [
        "﻿2026-08-21T14:50:02.6926856Z Current runner version: '2.336.0'",
        "2026-08-21T14:50:03.1002911Z ##[group]Run pytest -v",
        "2026-08-21T14:50:03.1003402Z \x1b[36;1mpytest -v\x1b[0m",
        "2026-08-21T14:50:03.1004216Z ##[endgroup]",
    ]
    + [f"2026-08-21T14:50:0{i}.0Z pad {i}" for i in range(4, 9)]
    + [
        "2026-08-21T14:50:10.0Z E   ModuleNotFoundError: No module named 'requests'",
        "2026-08-21T14:50:11.0Z ##[error]Process completed with exit code 1.",
    ]
)


def test_clean_strips_bom_timestamp_ansi_and_folds():
    assert _clean("﻿2026-08-21T14:50:02.6926856Z hello") == "hello"
    assert _clean("2026-08-21T14:50:03.1Z ##[group]Run pytest -v") == "Run pytest -v"
    assert _clean("2026-08-21T14:50:03.1Z ##[endgroup]") == ""
    assert _clean("2026-08-21T14:50:03.1Z \x1b[36;1mpytest\x1b[0m") == "pytest"


def test_error_annotation_is_kept_as_an_anchor():
    # ##[error] is GitHub's own marking of the failure — the one directive
    # worth keeping, and the most reliable anchor in a CI log.
    assert _clean("2026-08-21T14:50:11.0Z ##[error]exit code 1") == "##[error]exit code 1"
    out = isolate_error({"raw_log": GH_LOG})
    assert "##[error]" in out["log_markers"]


def test_real_format_log_isolates_the_failure():
    out = isolate_error({"raw_log": GH_LOG})
    region = out["error_region"]
    assert "ModuleNotFoundError" in region
    assert "2026-08-21T" not in region, "timestamps survived"
    assert "##[group]" not in region, "fold directives survived"
    assert "\x1b[" not in region, "ANSI survived"


def test_pick_prefers_the_failed_step():
    names = ["test/3_Set up job.txt", "test/5_Run tests.txt", "0_test.txt"]
    assert _pick(names, [("test", "Run tests")]) == ["test/5_Run tests.txt"]


def test_pick_falls_back_to_whole_job_logs():
    # Most archives have no per-step split: just "0_test.txt" at the root.
    names = ["0_test.txt", "test/system.txt"]
    assert _pick(names, [("test", "Run tests")]) == ["0_test.txt"]


def test_pick_always_drops_runner_diagnostics():
    # system.txt is runner chrome, never a failure signal.
    assert "test/system.txt" not in _pick(["0_test.txt", "test/system.txt"], [])


def test_fetch_log_prefers_a_supplied_raw_log():
    # Fixtures inject raw_log directly; the eval suites must stay offline and
    # must never need a token. Any fetch here would be a network call.
    assert fetch_log({"raw_log": "x", "repo": "a/b", "run_id": "1"}) == {}


def test_fetch_log_without_identity_reports_instead_of_raising():
    out = fetch_log({})
    assert "analysis_error" in out and "raw_log" not in out


def _zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, body in members.items():
            z.writestr(n, body)
    return buf.getvalue()


def test_fetch_run_log_concatenates_the_chosen_members(monkeypatch):
    from cidra.integrations import github

    monkeypatch.setattr(github, "_download_logs", lambda r, i: _zip(
        {"0_test.txt": "job body", "test/system.txt": "runner noise"}
    ))
    monkeypatch.setattr(github, "failed_steps", lambda r, i: [])
    out = github.fetch_run_log("o/r", 1)
    assert "job body" in out
    assert "runner noise" not in out


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
