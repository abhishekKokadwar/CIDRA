"""The cost line of a report: tokens times a price that is known, never a guess (ROADMAP M2)."""

import pytest

from cidra import config, evidence
from cidra.integrations import llm

pytestmark = pytest.mark.req("M2-COST")


def _calls(monkeypatch, *calls):
    llm.clear_latest_telemetry()
    for model, prompt, completion in calls:
        llm._latest_telemetry.append({"model": model, "tokens": {"prompt": prompt, "completion": completion,
                                                                 "total": prompt + completion}})
    monkeypatch.setattr(config, "PRICE_IN", None)
    monkeypatch.setattr(config, "PRICE_OUT", None)


def test_a_listed_model_is_costed_at_list_price(monkeypatch):
    _calls(monkeypatch, ("claude-haiku-4-5", 10_000, 1_000), ("anthropic/claude-haiku-4.5", 10_000, 1_000))
    cost, source = llm.run_cost()
    assert cost == pytest.approx(2 * (0.01 + 0.005)) and source == "list price"


def test_your_price_overrides_the_list(monkeypatch):
    _calls(monkeypatch, ("some-unlisted-model", 1_000_000, 100_000))
    monkeypatch.setattr(config, "PRICE_IN", 0.5)
    monkeypatch.setattr(config, "PRICE_OUT", 2.0)
    assert llm.run_cost() == (pytest.approx(0.7), "your price")


def test_an_unknown_model_gives_no_cost_not_a_partial_one(monkeypatch):
    _calls(monkeypatch, ("claude-haiku-4-5", 10_000, 1_000), ("gemini-3.5-flash", 10_000, 1_000))
    assert llm.run_cost() is None
    _calls(monkeypatch)
    assert llm.run_cost() is None  # no calls, no cost line


def test_the_evidence_block_shows_the_cost_and_its_source(monkeypatch):
    _calls(monkeypatch, ("claude-haiku-4-5", 12_000, 2_000))
    llm._requests_sent = 1
    monkeypatch.setattr(config, "MODEL_FIX", "claude-haiku-4-5")
    text = "\n".join(evidence.render({"image_tag": "img@sha256:x", "commit_sha": "abc"}))
    assert "1 requests, 12,000 prompt + 2,000 completion tokens, about $0.0220 at list price" in text
    llm.clear_latest_telemetry()
