"""Settings management and persistence for CIDRA.

Handles reading, updating, and validating .env variables, LLM credentials,
model assignments, and sandbox thresholds.
"""

import os
import time
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit

from cidra import config

ENV_PATH = Path(config.ENV_FILE).resolve()


# The only credential variables the settings API may write. Anything else in the
# payload is ignored: the endpoint must not be a way to set arbitrary env vars.
# Environment variable -> the cidra.config attribute that holds it.
_CONFIG_ATTR = {
    "CIDRA_API_KEY": "API_KEY",
    "CIDRA_BASE_URL": "BASE_URL",
    "GEMINI_API_KEY": "GEMINI_API_KEY",
    "CIDRA_GITHUB_TOKEN": "GITHUB_TOKEN",
    "CIDRA_GITHUB_TOKEN_RO": "GITHUB_TOKEN_RO",
    "CIDRA_WEBHOOK_SECRET": "WEBHOOK_SECRET",
}

ALLOWED_KEY_VARS = frozenset({
    "CIDRA_API_KEY",
    "GEMINI_API_KEY",
    "CIDRA_GITHUB_TOKEN",
    "CIDRA_GITHUB_TOKEN_RO",
    "CIDRA_WEBHOOK_SECRET",
})


def mask_secret(secret: str | None) -> str:
    """Mask a secret showing only prefix and suffix for UI security."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "••••••••"
    return f"{secret[:7]}••••••••{secret[-4:]}"


def parse_env_file(path: Path | None = None) -> Dict[str, str]:
    """Parse key-value pairs from .env."""
    target_path = path or ENV_PATH
    env_vars: Dict[str, str] = {}
    if not target_path.exists():
        return env_vars

    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


def write_env_file(updates: Dict[str, str], path: Path | None = None) -> None:
    """Update or append key-value pairs in .env while preserving comments."""
    target_path = path or ENV_PATH
    existing_lines = []
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    updated_keys = set()
    new_lines = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                # Replace with updated value
                new_lines.append(f"{k}={updates[k]}\n")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append any remaining new keys that were not already in .env
    for k, v in updates.items():
        if k not in updated_keys and v is not None:
            new_lines.append(f"{k}={v}\n")

    with open(target_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def get_current_settings() -> Dict[str, Any]:
    """Get active configuration with masked credentials and system stats."""
    env = parse_env_file()

    keys_list = [
        {
            "id": "cidra_api_key",
            # The endpoint actually configured, not a provider name guessed for it.
            "provider": urlsplit(env.get("CIDRA_BASE_URL") or config.BASE_URL).hostname or "Custom endpoint",
            "label": "Primary model endpoint (CIDRA_BASE_URL)",
            "envVar": "CIDRA_API_KEY",
            "masked": mask_secret(env.get("CIDRA_API_KEY") or config.API_KEY),
            "configured": bool(env.get("CIDRA_API_KEY") or config.API_KEY),
            "canTest": True,
            "baseUrl": env.get("CIDRA_BASE_URL", config.BASE_URL),
        },
        {
            "id": "gemini_api_key",
            "provider": "Google Gemini",
            "label": "Fallback when the primary call fails",
            "envVar": "GEMINI_API_KEY",
            "masked": mask_secret(env.get("GEMINI_API_KEY") or config.GEMINI_API_KEY),
            "configured": bool(env.get("GEMINI_API_KEY") or config.GEMINI_API_KEY),
            "canTest": True,
            "baseUrl": config.GEMINI_BASE_URL,
        },
        {
            "id": "github_token",
            "provider": "GitHub PAT (Read/Write)",
            "label": "Automated Pull Requests & Branches",
            "envVar": "CIDRA_GITHUB_TOKEN",
            "masked": mask_secret(env.get("CIDRA_GITHUB_TOKEN") or config.GITHUB_TOKEN),
            "configured": bool(env.get("CIDRA_GITHUB_TOKEN") or config.GITHUB_TOKEN),
            "canTest": True,
            "baseUrl": config.GITHUB_API,
        },
        {
            "id": "github_token_ro",
            "provider": "GitHub PAT (Read-Only)",
            "label": "Safe CI Log & Metadata Fetching",
            "envVar": "CIDRA_GITHUB_TOKEN_RO",
            "masked": mask_secret(env.get("CIDRA_GITHUB_TOKEN_RO") or config.read_token()),
            "configured": bool(env.get("CIDRA_GITHUB_TOKEN_RO") or config.read_token()),
            "canTest": True,
            "baseUrl": config.GITHUB_API,
        },
        {
            "id": "webhook_secret",
            "provider": "Webhook HMAC Secret",
            "label": "GitHub Webhook Delivery Verification",
            "envVar": "CIDRA_WEBHOOK_SECRET",
            "masked": mask_secret(env.get("CIDRA_WEBHOOK_SECRET") or config.WEBHOOK_SECRET),
            "configured": bool(env.get("CIDRA_WEBHOOK_SECRET") or config.WEBHOOK_SECRET),
            "canTest": False,
            "baseUrl": "",
        },
    ]

    models = {
        "model_analyze": env.get("CIDRA_MODEL_ANALYZE", config.MODEL_ANALYZE),
        "model_fix": env.get("CIDRA_MODEL_FIX", config.MODEL_FIX),
        "base_url": env.get("CIDRA_BASE_URL", config.BASE_URL),
        "fallback_model": config.FALLBACK_MODEL,
    }

    flakiness = {
        # The values in effect, after their bounds (config.BOUNDS).
        "flaky_runs": config.FLAKY_RUNS,
        "flaky_score_threshold": config.FLAKY_SCORE_THRESHOLD,
        "max_fix_attempts": config.MAX_FIX_ATTEMPTS,
        "container_timeout": config.CONTAINER_TIMEOUT,
        "enable_pr_creation": env.get("CIDRA_ENABLE_PR_CREATION", str(config.ENABLE_PR_CREATION)).lower() == "true",
        "practice_repo": env.get("CIDRA_PRACTICE_REPO_SLUG", "helpmecode69/cidra-practice"),
    }

    system = {
        "python_version": "3.11.0",
        "framework": "LangGraph Core",
        "idempotency_db": config.IDEMPOTENCY_DB,
        "worktree_root": config.WORKTREE_ROOT,
        "fix_cache_path": config.FIX_CACHE_PATH,
        "run_history_path": config.RUN_HISTORY_PATH,
        "status": "operational",
    }

    return {
        "keys": keys_list,
        "models": models,
        "flakiness": flakiness,
        "system": system,
    }


def save_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist updated settings to .env and reload config variables in memory."""
    updates: Dict[str, str] = {}

    # Extract keys
    keys_input = payload.get("keys", {})
    if isinstance(keys_input, dict):
        for k, v in keys_input.items():
            if k not in ALLOWED_KEY_VARS or not isinstance(v, str):
                continue
            if v and not v.startswith("••••") and "••••" not in v:
                updates[k] = v

    # Extract models
    models_input = payload.get("models", {})
    if "model_analyze" in models_input:
        updates["CIDRA_MODEL_ANALYZE"] = str(models_input["model_analyze"])
    if "model_fix" in models_input:
        updates["CIDRA_MODEL_FIX"] = str(models_input["model_fix"])
    if "base_url" in models_input and urlsplit(str(models_input["base_url"])).scheme in ("http", "https"):
        updates["CIDRA_BASE_URL"] = str(models_input["base_url"])

    # Extract flakiness & sandbox
    flakiness_input = payload.get("flakiness", {})
    if "flaky_runs" in flakiness_input:
        updates["FLAKY_RUNS"] = str(flakiness_input["flaky_runs"])
    if "flaky_score_threshold" in flakiness_input:
        updates["FLAKY_SCORE_THRESHOLD"] = str(flakiness_input["flaky_score_threshold"])
    if "max_fix_attempts" in flakiness_input:
        updates["MAX_FIX_ATTEMPTS"] = str(flakiness_input["max_fix_attempts"])
    if "container_timeout" in flakiness_input:
        updates["CONTAINER_TIMEOUT"] = str(flakiness_input["container_timeout"])
    if "enable_pr_creation" in flakiness_input:
        updates["CIDRA_ENABLE_PR_CREATION"] = "true" if flakiness_input["enable_pr_creation"] else "false"
    if "practice_repo" in flakiness_input:
        updates["CIDRA_PRACTICE_REPO_SLUG"] = str(flakiness_input["practice_repo"])

    # One value per line in .env: a line break in a value would smuggle in a
    # second variable.
    updates = {k: v for k, v in updates.items() if "\n" not in v and "\r" not in v}

    if updates:
        write_env_file(updates)

        # Update os.environ and cidra.config
        for k, v in updates.items():
            os.environ[k] = v

        # Every saved key reaches the running server; its readers look them up at
        # call time (G-19: before, only the connection test saw a new key).
        for var, attr in _CONFIG_ATTR.items():
            if var in updates:
                setattr(config, attr, updates[var])
        if "CIDRA_MODEL_ANALYZE" in updates:
            config.MODEL_ANALYZE = updates["CIDRA_MODEL_ANALYZE"]
        if "CIDRA_MODEL_FIX" in updates:
            config.MODEL_FIX = updates["CIDRA_MODEL_FIX"]
        for var, bounds in config.BOUNDS.items():
            if var in updates:
                setattr(config, var, config.bounded(updates[var], *bounds))
        if "CIDRA_ENABLE_PR_CREATION" in updates:
            config.ENABLE_PR_CREATION = updates["CIDRA_ENABLE_PR_CREATION"].lower() == "true"

    return get_current_settings()


def test_provider(provider_id: str) -> Dict[str, Any]:
    """Test connectivity and measure round-trip latency to a provider."""
    env = parse_env_file()
    start_time = time.time()

    try:
        if provider_id in ("cidra_api_key", "gemini_api_key"):
            if provider_id == "cidra_api_key":
                key = env.get("CIDRA_API_KEY") or config.API_KEY
                base = env.get("CIDRA_BASE_URL") or config.BASE_URL
                model = env.get("CIDRA_MODEL_FIX") or config.MODEL_FIX
            else:
                key = env.get("GEMINI_API_KEY") or config.GEMINI_API_KEY
                base, model = config.GEMINI_BASE_URL, config.FALLBACK_MODEL
            if not key:
                return {"ok": False, "error": "No API key set"}
            # The call CIDRA makes, capped at one token: it checks the key, the
            # endpoint and the model id together. A model list would not: some
            # providers serve it without a key, and it says nothing of the id.
            req = urllib.request.Request(
                base.rstrip("/") + "/chat/completions", method="POST",
                data=json.dumps({"model": model, "max_tokens": 1,
                                 "messages": [{"role": "user", "content": "ping"}]}).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                         "User-Agent": "CIDRA/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000)
                return {"ok": True, "latency_ms": elapsed_ms, "status": resp.status,
                        "message": f"{urlsplit(base).hostname} answered with {model}"}

        elif provider_id in ("github_token", "github_token_ro"):
            token = (
                env.get("CIDRA_GITHUB_TOKEN") or config.GITHUB_TOKEN
                if provider_id == "github_token"
                else env.get("CIDRA_GITHUB_TOKEN_RO") or config.read_token()
            )
            if not token:
                return {"ok": False, "error": "No GitHub PAT configured"}
            req = urllib.request.Request(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "CIDRA/1.0",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000)
                return {"ok": True, "latency_ms": elapsed_ms, "status": resp.status, "message": "GitHub API verified"}

        return {"ok": False, "error": f"Unknown provider: {provider_id}"}

    except urllib.error.HTTPError as e:
        elapsed_ms = round((time.time() - start_time) * 1000)
        return {"ok": False, "latency_ms": elapsed_ms, "status": e.code, "error": f"HTTP {e.code}: {_provider_error(e)}"}
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000)
        return {"ok": False, "latency_ms": elapsed_ms, "error": str(e)}


def _provider_error(e: urllib.error.HTTPError) -> str:
    """The provider's own message ("No endpoints found for ...", "Invalid API Key"),
    which says what to fix; the HTTP reason phrase alone does not."""
    try:
        err = json.loads(e.read()).get("error")
        msg = err.get("message") if isinstance(err, dict) else err
        return str(msg)[:200] if msg else str(e.reason)
    except Exception:  # noqa: BLE001 - any unreadable body falls back to the reason
        return str(e.reason)
