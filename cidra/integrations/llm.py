"""LLM client. See docs/4_architecture.md §5 node 3.

Only two nodes call an LLM (analyze, generate_fix). Both go through here so
model choice, forced-tool-call and validation live in one place.

Provider-agnostic on purpose: CIDRA_BASE_URL points at OpenRouter today and
can point at any OpenAI-compatible endpoint later. Only .env changes.
"""

from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from cidra.config import API_KEY, BASE_URL

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("CIDRA_API_KEY is not set — see .env.example")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def structured(
    *,
    model: str,
    schema: Type[T],
    system: str,
    user: str,
    max_tokens: int = 2048,
) -> T:
    """One call, forced through a tool schema, validated by Pydantic.

    Raises on a shape we can't trust. The caller decides whether to retry —
    see routers.route_after_validate.
    """
    resp = client().chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "report",
                    "description": f"Report the result as {schema.__name__}.",
                    "parameters": schema.model_json_schema(),
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "report"}},
    )
    calls = resp.choices[0].message.tool_calls
    if not calls:
        raise ValueError(f"{model} returned no tool call: {resp.choices[0].message.content!r}")
    return schema.model_validate_json(calls[0].function.arguments)


if __name__ == "__main__":
    # Phase 0 exit criterion: one validated structured call.
    from cidra.config import MODEL_ANALYZE
    from cidra.state import Analysis

    out = structured(
        model=MODEL_ANALYZE,
        schema=Analysis,
        system="You classify CI failures. Be terse.",
        user="ModuleNotFoundError: No module named 'requests'\nFile test_api.py, line 3",
    )
    print(out.model_dump_json(indent=2))
