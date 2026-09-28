"""LLM client. See docs/4_architecture.md §5 node 3.

Only two nodes call an LLM (analyze, generate_fix). Both go through here so
model choice, forced-tool-call and validation live in one place.

Provider-agnostic on purpose: CIDRA_BASE_URL points at OpenRouter today and
can point at any OpenAI-compatible endpoint later. Only .env changes.
"""

from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from cidra.config import API_KEY, BASE_URL, NVIDIA_API_KEY_KIMI, NVIDIA_API_KEY_GLM, NVIDIA_BASE_URL, GROQ_API_KEY, GROQ_BASE_URL

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None
_kimi_client: OpenAI | None = None
_glm_client: OpenAI | None = None
_groq_client: OpenAI | None = None

def client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("CIDRA_API_KEY is not set — see .env.example")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=30.0)
    return _client

def kimi_client() -> OpenAI:
    global _kimi_client
    if _kimi_client is None:
        if not NVIDIA_API_KEY_KIMI:
            raise RuntimeError("NVIDIA_API_KEY_KIMI is not set for fallback")
        _kimi_client = OpenAI(api_key=NVIDIA_API_KEY_KIMI, base_url=NVIDIA_BASE_URL, timeout=30.0)
    return _kimi_client

def glm_client() -> OpenAI:
    global _glm_client
    if _glm_client is None:
        if not NVIDIA_API_KEY_GLM:
            raise RuntimeError("NVIDIA_API_KEY_GLM is not set for fallback")
        _glm_client = OpenAI(api_key=NVIDIA_API_KEY_GLM, base_url=NVIDIA_BASE_URL, timeout=30.0)
    return _glm_client

def groq_client() -> OpenAI:
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set for fallback")
        _groq_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=30.0)
    return _groq_client


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
    # Fallback priority based on model speed & accuracy:
    # 1. moonshotai/kimi-k3 (Fastest)
    # 2. z-ai/glm-5.3-flash
    # 3. z-ai/glm-5.3
    # 4. OpenRouter model (the 'model' argument)
    models_to_try = [
        ("llama-3.3-70b-versatile", groq_client),
        ("moonshotai/kimi-k3", kimi_client),
        ("z-ai/glm-5.3-flash", glm_client),
        ("z-ai/glm-5.3", glm_client),
        (model, client),
    ]

    last_error = None
    
    for attempt_model, get_client in models_to_try:
        try:
            print(f"Attempting inference with {attempt_model}...")
            resp = get_client().chat.completions.create(
                model=attempt_model,
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
                raise ValueError(f"{attempt_model} returned no tool call: {resp.choices[0].message.content!r}")
            return schema.model_validate_json(calls[0].function.arguments)
        except Exception as e:
            print(f"Model {attempt_model} failed: {e}")
            last_error = e

    # If all fallbacks fail, raise the last error so the graph can gracefully abort
    raise last_error


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
