"""One fallback, Gemini, and only when its key is set and the primary is not
Gemini already. The old chain of five providers had gone dead (retired or
unknown models) and burned free-tier quotas."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from cidra.integrations import llm


class Answer(BaseModel):
    ok: bool


class Failing(Exception):
    status_code = 404  # permanent: no retry, straight to the next model


def _client(seen, fail):
    def create(model, **kwargs):
        seen.append(model)
        if fail:
            raise Failing("unknown model")
        call = SimpleNamespace(function=SimpleNamespace(arguments='{"ok": true}'))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
                               usage=None)
    return lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _setup(monkeypatch, *, gemini_key, base_url, primary_fails=True):
    seen = []
    llm.clear_latest_telemetry()
    monkeypatch.setattr(llm, "client", _client(seen, primary_fails))
    monkeypatch.setattr(llm, "gemini_client", _client(seen, False))
    monkeypatch.setattr(llm.config, "GEMINI_API_KEY", gemini_key)
    monkeypatch.setattr(llm.config, "BASE_URL", base_url)
    monkeypatch.setattr(llm.config, "FALLBACK_MODEL", "gemini-fallback")
    return seen


def _ask():
    return llm.structured(model="primary", schema=Answer, system="s", user="u")


def test_a_failed_primary_falls_back_to_gemini_once(monkeypatch):
    seen = _setup(monkeypatch, gemini_key="AIza-x", base_url="https://api.anthropic.com/v1/")
    assert _ask().ok and seen == ["primary", "gemini-fallback"]


def test_no_fallback_without_a_gemini_key(monkeypatch):
    seen = _setup(monkeypatch, gemini_key="", base_url="https://api.anthropic.com/v1/")
    with pytest.raises(Failing):
        _ask()
    assert seen == ["primary"]


def test_a_gemini_primary_is_not_its_own_fallback(monkeypatch):
    seen = _setup(monkeypatch, gemini_key="AIza-x", base_url=llm.config.GEMINI_BASE_URL)
    with pytest.raises(Failing):
        _ask()
    assert seen == ["primary"]
