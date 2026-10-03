"""LLM client. See docs/4_architecture.md §5 node 3.

Only two nodes call an LLM (analyze, generate_fix). Both go through here so
model choice, forced-tool-call and validation live in one place.

Provider-agnostic on purpose: CIDRA_BASE_URL points at OpenRouter today and
can point at any OpenAI-compatible endpoint later. Only .env changes.
"""

import logging
import time
from typing import Type, TypeVar

from openai import OpenAI
from openai import RateLimitError
from pydantic import BaseModel

from cidra.config import (
    API_KEY, BASE_URL, 
    OPENROUTER_API_KEY, OPENROUTER_API_KEY_2, OPENROUTER_BASE_URL,
    NVIDIA_API_KEY_KIMI, NVIDIA_API_KEY_GLM, NVIDIA_BASE_URL, 
    GROQ_API_KEY, GROQ_BASE_URL
)

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger("cidra.llm")

# The request itself is wrong for this provider (bad key, no credit, unknown
# model, rejected schema). Retrying cannot help, so move to the next provider.
_NO_RETRY_STATUS = {400, 401, 402, 403, 404, 422}

_client: OpenAI | None = None
_or_client_1: OpenAI | None = None
_or_client_2: OpenAI | None = None
_kimi_client: OpenAI | None = None
_glm_client: OpenAI | None = None
_groq_client: OpenAI | None = None

_latest_telemetry: list[dict] = []

def get_latest_telemetry() -> list[dict]:
    return list(_latest_telemetry)

def clear_latest_telemetry():
    _latest_telemetry.clear()

def client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("CIDRA_API_KEY is not set — see .env.example")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=120.0)
    return _client

def openrouter_client_1() -> OpenAI:
    global _or_client_1
    if _or_client_1 is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set for fallback")
        _or_client_1 = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL, timeout=120.0)
    return _or_client_1

def openrouter_client_2() -> OpenAI:
    global _or_client_2
    if _or_client_2 is None:
        if not OPENROUTER_API_KEY_2:
            raise RuntimeError("OPENROUTER_API_KEY_2 is not set for fallback")
        _or_client_2 = OpenAI(api_key=OPENROUTER_API_KEY_2, base_url=OPENROUTER_BASE_URL, timeout=120.0)
    return _or_client_2

def kimi_client() -> OpenAI:
    global _kimi_client
    if _kimi_client is None:
        if not NVIDIA_API_KEY_KIMI:
            raise RuntimeError("NVIDIA_API_KEY_KIMI is not set for fallback")
        _kimi_client = OpenAI(api_key=NVIDIA_API_KEY_KIMI, base_url=NVIDIA_BASE_URL, timeout=120.0)
    return _kimi_client

def glm_client() -> OpenAI:
    global _glm_client
    if _glm_client is None:
        if not NVIDIA_API_KEY_GLM:
            raise RuntimeError("NVIDIA_API_KEY_GLM is not set for fallback")
        _glm_client = OpenAI(api_key=NVIDIA_API_KEY_GLM, base_url=NVIDIA_BASE_URL, timeout=120.0)
    return _glm_client

def groq_client() -> OpenAI:
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set for fallback")
        _groq_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=120.0)
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
    # BYOK: the primary call uses the caller's model (CIDRA_MODEL_ANALYZE /
    # CIDRA_MODEL_FIX) against CIDRA_BASE_URL. The fallbacks below are other
    # providers, so each carries its own provider-specific model id:
    # 2-3. OpenRouter Key 2
    # 4. Groq
    # 5-6. NVIDIA NIM
    fallbacks = [
        ("meta-llama/llama-3.1-70b-instruct", openrouter_client_2, OPENROUTER_API_KEY_2),
        ("qwen/qwen-2.5-72b-instruct", openrouter_client_2, OPENROUTER_API_KEY_2),
        ("llama-3.1-8b-instant", groq_client, GROQ_API_KEY),
        ("moonshotai/kimi-k3", kimi_client, NVIDIA_API_KEY_KIMI),
        ("z-ai/glm-5.3-flash", glm_client, NVIDIA_API_KEY_GLM),
    ]
    # A fallback with no key configured is not in the chain at all.
    models_to_try = [(model, client)] + [(m, c) for m, c, key in fallbacks if key]

    last_error = None
    
    for attempt_model, get_client in models_to_try:
        max_retries = 3
        for retry in range(max_retries):
            try:
                log.info("Attempting inference with %s (try %d/%d)", attempt_model, retry + 1, max_retries)
                start_time = time.time()
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
                elapsed = time.time() - start_time
                calls = resp.choices[0].message.tool_calls
                if not calls:
                    raise ValueError(f"{attempt_model} returned no tool call: {resp.choices[0].message.content!r}")
                
                # Record real telemetry for dashboard transparency
                usage = getattr(resp, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
                completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
                total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) if usage else 0
                
                _latest_telemetry.append({
                    "model": attempt_model,
                    "latency_s": round(elapsed, 2),
                    "tokens": {
                        "prompt": prompt_tokens,
                        "completion": completion_tokens,
                        "total": total_tokens,
                    },
                    "tool_name": "report",
                    "tool_args": calls[0].function.arguments,
                    "system_prompt": system,
                    "user_prompt": user,
                    "timestamp": round(time.time(), 2)
                })

                return schema.model_validate_json(calls[0].function.arguments)
            except Exception as e:
                log.warning("Model %s failed (attempt %d/%d): %s",
                            attempt_model, retry + 1, max_retries, str(e)[:300])
                last_error = e

                if getattr(e, "status_code", None) in _NO_RETRY_STATUS:
                    break  # Move to next fallback model
                
                # Check for rate limit explicitly
                is_rate_limit = isinstance(e, RateLimitError) or (hasattr(e, 'status_code') and e.status_code == 429) or (hasattr(e, 'message') and '429' in str(e.message)) or '429' in str(e)
                
                if retry < max_retries - 1:
                    if is_rate_limit:
                        log.info("Hit rate limit. Backing off for 65s to clear quota window...")
                        time.sleep(65)
                    else:
                        log.info("Transient error. Backing off for 2s...")
                        time.sleep(2)
                    continue # Retry the same model
                else:
                    log.warning("Model %s exhausted all %d retries.", attempt_model, max_retries)
                    break # Move to next fallback model

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
