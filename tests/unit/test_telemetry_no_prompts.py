"""The telemetry CIDRA exports (the dashboard's /telemetry.json, and the file the
bot workflow uploads as an artifact) carries counts, never what the model was
shown or said: prompts hold CI log excerpts and source code (KNOWN_GAPS G-20).
The full state, prompts included, stays in run_states/, which git ignores."""

import json
import subprocess

import pytest

from cidra import config, history

pytestmark = pytest.mark.req("G-20")

SECRET_SYSTEM, SECRET_USER, SECRET_ARGS, SECRET_LOG = (
    "SYSTEM-PROMPT-MARKER", "USER-PROMPT-WITH-SOURCE-MARKER", "TOOL-ARGS-MARKER", "RAW-LOG-MARKER")


def test_exported_telemetry_has_no_prompt_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dashboard" / "public").mkdir(parents=True)
    monkeypatch.setattr(config, "RUN_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    call = {"model": "m", "latency_s": 1.0, "tokens": {"prompt": 10, "completion": 5, "total": 15},
            "tool_name": "report", "tool_args": SECRET_ARGS, "system_prompt": SECRET_SYSTEM,
            "user_prompt": SECRET_USER, "timestamp": 0}
    state = {"run_id": "r1", "repo": "o/r", "outcome": "diagnosis_only", "raw_log": SECRET_LOG,
             "llm_telemetry": [call]}
    assert history.record(state)

    exported = (tmp_path / "dashboard" / "public" / "telemetry.json").read_text(encoding="utf-8")
    assert json.loads(exported)["runs"], "the run must be in the export for this test to mean anything"
    assert json.dumps(history.dashboard_telemetry())  # the live endpoint builds the same view
    for marker in (SECRET_SYSTEM, SECRET_USER, SECRET_ARGS, SECRET_LOG):
        assert marker not in exported
        assert marker not in json.dumps(history.dashboard_telemetry())
    # kept locally for the run's own detail view, and never committed
    assert SECRET_USER in (tmp_path / "run_states" / "r1.json").read_text(encoding="utf-8")


def test_the_files_that_hold_prompts_are_ignored_by_git():
    out = subprocess.run(["git", "check-ignore", "run_states/r1.json", "cidra_run_history.jsonl"],
                         capture_output=True, text=True)
    assert out.stdout.split() == ["run_states/r1.json", "cidra_run_history.jsonl"]
