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
