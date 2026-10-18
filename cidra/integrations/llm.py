"""LLM client. See docs/4_architecture.md §5 node 3.

Only two nodes call an LLM (analyze, generate_fix). Both go through here so
model choice, forced-tool-call and validation live in one place.

Provider-agnostic on purpose: CIDRA_BASE_URL can point at any OpenAI-compatible
endpoint. Only .env changes.
"""

import logging
import time
from typing import Type, TypeVar

from openai import OpenAI
from openai import RateLimitError
from pydantic import BaseModel

from cidra.config import API_KEY, BASE_URL, FALLBACK_MODEL, GEMINI_API_KEY, GEMINI_BASE_URL

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger("cidra.llm")

# The request itself is wrong for this provider (bad key, no credit, unknown
# model, rejected schema). Retrying cannot help, so move to the next provider.
_NO_RETRY_STATUS = {400, 401, 402, 403, 404, 422}

_client: OpenAI | None = None
_gemini_client: OpenAI | None = None

_latest_telemetry: list[dict] = []
_requests_sent = 0  # every request this run, including ones that failed


class BudgetExceeded(RuntimeError):
    """The run hit its LLM spend cap (CIDRA_MAX_LLM_CALLS / CIDRA_MAX_LLM_TOKENS)."""


def get_latest_telemetry() -> list[dict]:
    return list(_latest_telemetry)

def clear_latest_telemetry():
    global _requests_sent
    _latest_telemetry.clear()
    _requests_sent = 0


def usage_summary() -> dict:
    """What this run has spent so far: requests sent and tokens billed."""
    return {
        "requests": _requests_sent,
        "prompt_tokens": sum(c["tokens"]["prompt"] for c in _latest_telemetry),
        "completion_tokens": sum(c["tokens"]["completion"] for c in _latest_telemetry),
        "total_tokens": sum(c["tokens"]["total"] for c in _latest_telemetry),
    }


# List prices in USD per million (prompt, completion) tokens, only for models whose
# price is confirmed. ponytail: a hand-kept table goes stale; CIDRA_PRICE_IN /
# CIDRA_PRICE_OUT override it, and a model not listed shows no cost, never a guess.
LIST_PRICES = {"claude-haiku-4-5": (1.0, 5.0)}


def _price(model: str) -> tuple[tuple[float, float] | None, str | None]:
    from cidra import config  # read at call time, like the model settings
    if config.PRICE_IN is not None and config.PRICE_OUT is not None:
        return (config.PRICE_IN, config.PRICE_OUT), "your price"
    name = model.lower().rsplit("/", 1)[-1].replace(".", "-")  # "anthropic/claude-haiku-4.5" too
    for key, price in LIST_PRICES.items():
        if name.startswith(key):
            return price, "list price"
    return None, None


def run_cost() -> tuple[float, str] | None:
    """(USD, where the price came from) for this run's calls, or None when there
    were none or any call's model has no known price: a partial sum would mislead."""
    if not _latest_telemetry:
        return None
    total, source = 0.0, None
    for call in _latest_telemetry:
        price, source = _price(call["model"])
        if price is None:
            return None
        total += call["tokens"]["prompt"] / 1e6 * price[0] + call["tokens"]["completion"] / 1e6 * price[1]
    return total, source


def _check_budget() -> None:
    """Refuse the next request once the run's cap is reached. The caps are per
    run (reset by clear_latest_telemetry) and bound the worst case: retries,
    fallbacks and fix attempts all draw from the same allowance."""
    from cidra import config  # read at call time, like the model settings
    used = usage_summary()
    if used["requests"] >= config.MAX_LLM_CALLS:
        raise BudgetExceeded(f"LLM request cap reached ({config.MAX_LLM_CALLS} per run)")
    if used["total_tokens"] >= config.MAX_LLM_TOKENS:
        raise BudgetExceeded(f"LLM token cap reached ({config.MAX_LLM_TOKENS} per run)")

def client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("CIDRA_API_KEY is not set — see .env.example")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=120.0)
    return _client

def gemini_client() -> OpenAI:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL, timeout=120.0)
    return _gemini_client


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
    # CIDRA_MODEL_FIX) against CIDRA_BASE_URL. One fallback, Gemini, when its key
    # is set and the primary is not Gemini already.
    models_to_try = [(model, client)]
    if GEMINI_API_KEY and BASE_URL.rstrip("/") != GEMINI_BASE_URL.rstrip("/"):
        models_to_try.append((FALLBACK_MODEL, gemini_client))

    last_error = None
    
    for attempt_model, get_client in models_to_try:
        max_retries = 3
        for retry in range(max_retries):
            _check_budget()  # outside the try: a spent budget is not retried
            try:
                global _requests_sent
                _requests_sent += 1
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

                # Record real telemetry for dashboard transparency. Recorded before
                # the shape check: a reply with no tool call was still billed.
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
                    "tool_args": calls[0].function.arguments if calls else None,
                    "system_prompt": system,
                    "user_prompt": user,
                    "timestamp": round(time.time(), 2)
                })

                if not calls:
                    raise ValueError(f"{attempt_model} returned no tool call: {resp.choices[0].message.content!r}")
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
