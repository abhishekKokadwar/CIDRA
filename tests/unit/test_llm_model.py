"""BYOK: the primary LLM call must send the caller's configured model."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from cidra.integrations import llm


class _Out(BaseModel):
    ok: bool


def test_structured_sends_configured_model():
    fake = MagicMock()
    call = SimpleNamespace(function=SimpleNamespace(arguments='{"ok": true}'))
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
        usage=None,
    )
    with patch.object(llm, "client", return_value=fake):
        out = llm.structured(model="my/own-model", schema=_Out, system="s", user="u")

    assert out.ok is True
    assert fake.chat.completions.create.call_args.kwargs["model"] == "my/own-model"


def _reply(tool_calls, prompt=10, completion=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=tool_calls, content="x"))],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                              total_tokens=prompt + completion),
    )


def test_request_cap_stops_the_run_and_counts_failed_replies(monkeypatch):
    import pytest
    from cidra import config

    monkeypatch.setattr(config, "MAX_LLM_CALLS", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    llm.clear_latest_telemetry()
    fake = MagicMock()
    fake.chat.completions.create.return_value = _reply(None)  # billed, but no tool call
    with patch.object(llm, "client", return_value=fake):
        with pytest.raises(llm.BudgetExceeded):
            llm.structured(model="m", schema=_Out, system="s", user="u")

    assert fake.chat.completions.create.call_count == 2  # the cap, not 3 retries
    assert llm.usage_summary() == {
        "requests": 2, "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    llm.clear_latest_telemetry()
    assert llm.usage_summary()["requests"] == 0


def test_token_cap_stops_the_next_request(monkeypatch):
    import pytest
    from cidra import config

    monkeypatch.setattr(config, "MAX_LLM_TOKENS", 15)
    llm.clear_latest_telemetry()
    call = SimpleNamespace(function=SimpleNamespace(arguments='{"ok": true}'))
    fake = MagicMock()
    fake.chat.completions.create.return_value = _reply([call])
    with patch.object(llm, "client", return_value=fake):
        llm.structured(model="m", schema=_Out, system="s", user="u")  # spends 15
        with pytest.raises(llm.BudgetExceeded):
            llm.structured(model="m", schema=_Out, system="s", user="u")
    assert fake.chat.completions.create.call_count == 1
    llm.clear_latest_telemetry()
