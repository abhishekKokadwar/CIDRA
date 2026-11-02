"""A coding agent's model calls are counted as requests, and each pilot case keeps
the raw token counts and models the key proxy saw (ROADMAP M7): the first real
run (bip-thefuck-2) reported 0 requests and only price-weighted tokens."""

import pytest

from cidra.integrations import llm
from eval.attempts import agent_usage

pytestmark = pytest.mark.req("M7-CLAUDE-CODE")

CALLS = [{"model": "claude-sonnet-4-5", "input_tokens": 10, "cache_creation_input_tokens": 4000,
          "cache_read_input_tokens": 20000, "output_tokens": 300},
         {"model": "claude-haiku-4-5", "input_tokens": 5, "output_tokens": 20}]


def test_each_agent_call_is_a_request_and_its_raw_tokens_are_kept():
    llm.clear_latest_telemetry()
    try:
        for usage in CALLS:
            llm.record_usage(usage, tool_name="claude-code")
        assert llm.usage_summary()["requests"] == 2
        assert agent_usage(llm.get_latest_telemetry()) == {
            "calls": 2, "models": ["claude-haiku-4-5", "claude-sonnet-4-5"], "input_tokens": 15,
            "cache_creation_input_tokens": 4000, "cache_read_input_tokens": 20000, "output_tokens": 320}
    finally:
        llm.clear_latest_telemetry()


def test_a_built_in_run_has_no_agent_usage():
    assert agent_usage([{"tool_name": "Patch", "tokens": {"prompt": 900, "completion": 80}}]) is None
