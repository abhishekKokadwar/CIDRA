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

from cidra import config

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


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
            "provider": "OpenRouter",
            "label": "Primary LLM Inference Gateway",
            "envVar": "CIDRA_API_KEY",
            "masked": mask_secret(env.get("CIDRA_API_KEY") or config.API_KEY),
            "configured": bool(env.get("CIDRA_API_KEY") or config.API_KEY),
            "canTest": True,
            "baseUrl": env.get("CIDRA_BASE_URL", config.BASE_URL),
        },
        {
            "id": "nvidia_kimi",
            "provider": "NVIDIA NIM (Kimi)",
            "label": "Fast Fallback Tier 1",
            "envVar": "NVIDIA_API_KEY_KIMI",
            "masked": mask_secret(env.get("NVIDIA_API_KEY_KIMI") or config.NVIDIA_API_KEY_KIMI),
            "configured": bool(env.get("NVIDIA_API_KEY_KIMI") or config.NVIDIA_API_KEY_KIMI),
            "canTest": True,
            "baseUrl": config.NVIDIA_BASE_URL,
        },
        {
            "id": "nvidia_glm",
            "provider": "NVIDIA NIM (GLM)",
            "label": "Fast Fallback Tier 2",
            "envVar": "NVIDIA_API_KEY_GLM",
            "masked": mask_secret(env.get("NVIDIA_API_KEY_GLM") or config.NVIDIA_API_KEY_GLM),
            "configured": bool(env.get("NVIDIA_API_KEY_GLM") or config.NVIDIA_API_KEY_GLM),
            "canTest": True,
            "baseUrl": config.NVIDIA_BASE_URL,
        },
        {
            "id": "groq_api_key",
            "provider": "Groq Cloud",
            "label": "Ultra-Fast LPU Inference",
            "envVar": "GROQ_API_KEY",
            "masked": mask_secret(env.get("GROQ_API_KEY") or config.GROQ_API_KEY),
            "configured": bool(env.get("GROQ_API_KEY") or config.GROQ_API_KEY),
            "canTest": True,
            "baseUrl": config.GROQ_BASE_URL,
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
            "masked": mask_secret(env.get("CIDRA_GITHUB_TOKEN_RO") or config.GITHUB_TOKEN_RO),
            "configured": bool(env.get("CIDRA_GITHUB_TOKEN_RO") or config.GITHUB_TOKEN_RO),
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
        "nvidia_base_url": config.NVIDIA_BASE_URL,
        "groq_base_url": config.GROQ_BASE_URL,
    }

    flakiness = {
        "flaky_runs": int(env.get("FLAKY_RUNS", config.FLAKY_RUNS)),
        "flaky_score_threshold": int(env.get("FLAKY_SCORE_THRESHOLD", config.FLAKY_SCORE_THRESHOLD)),
        "max_fix_attempts": int(env.get("MAX_FIX_ATTEMPTS", config.MAX_FIX_ATTEMPTS)),
        "container_timeout": int(env.get("CONTAINER_TIMEOUT", 60)),
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
            if v and not v.startswith("••••") and "••••" not in v:
                updates[k] = v

    # Extract models
    models_input = payload.get("models", {})
    if "model_analyze" in models_input:
        updates["CIDRA_MODEL_ANALYZE"] = str(models_input["model_analyze"])
    if "model_fix" in models_input:
        updates["CIDRA_MODEL_FIX"] = str(models_input["model_fix"])
    if "base_url" in models_input:
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

    if updates:
        write_env_file(updates)

        # Update os.environ and cidra.config
        for k, v in updates.items():
            os.environ[k] = v

        if "CIDRA_API_KEY" in updates:
            config.API_KEY = updates["CIDRA_API_KEY"]
        if "CIDRA_MODEL_ANALYZE" in updates:
            config.MODEL_ANALYZE = updates["CIDRA_MODEL_ANALYZE"]
        if "CIDRA_MODEL_FIX" in updates:
            config.MODEL_FIX = updates["CIDRA_MODEL_FIX"]
        if "FLAKY_RUNS" in updates:
            config.FLAKY_RUNS = int(updates["FLAKY_RUNS"])
        if "FLAKY_SCORE_THRESHOLD" in updates:
            config.FLAKY_SCORE_THRESHOLD = int(updates["FLAKY_SCORE_THRESHOLD"])
        if "MAX_FIX_ATTEMPTS" in updates:
            config.MAX_FIX_ATTEMPTS = int(updates["MAX_FIX_ATTEMPTS"])
        if "CIDRA_ENABLE_PR_CREATION" in updates:
            config.ENABLE_PR_CREATION = updates["CIDRA_ENABLE_PR_CREATION"].lower() == "true"

    return get_current_settings()


def test_provider(provider_id: str) -> Dict[str, Any]:
    """Test connectivity and measure round-trip latency to a provider."""
    env = parse_env_file()
    start_time = time.time()

    try:
        if provider_id == "cidra_api_key":
            key = env.get("CIDRA_API_KEY") or config.API_KEY
            if not key:
                return {"ok": False, "error": "No API key configured for OpenRouter"}
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "CIDRA/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000)
                return {"ok": True, "latency_ms": elapsed_ms, "status": resp.status, "message": "OpenRouter verified"}

        elif provider_id in ("nvidia_kimi", "nvidia_glm"):
            key = (
                env.get("NVIDIA_API_KEY_KIMI") or config.NVIDIA_API_KEY_KIMI
                if provider_id == "nvidia_kimi"
                else env.get("NVIDIA_API_KEY_GLM") or config.NVIDIA_API_KEY_GLM
            )
            if not key:
                return {"ok": False, "error": "No NVIDIA API key configured"}
            req = urllib.request.Request(
                "https://integrate.api.nvidia.com/v1/models",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "CIDRA/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000)
                return {"ok": True, "latency_ms": elapsed_ms, "status": resp.status, "message": "NVIDIA NIM verified"}

        elif provider_id == "groq_api_key":
            key = env.get("GROQ_API_KEY") or config.GROQ_API_KEY
            if not key:
                return {"ok": False, "error": "No Groq API key configured"}
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "CIDRA/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000)
                return {"ok": True, "latency_ms": elapsed_ms, "status": resp.status, "message": "Groq LPU verified"}

        elif provider_id in ("github_token", "github_token_ro"):
            token = (
                env.get("CIDRA_GITHUB_TOKEN") or config.GITHUB_TOKEN
                if provider_id == "github_token"
                else env.get("CIDRA_GITHUB_TOKEN_RO") or config.GITHUB_TOKEN_RO
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
        return {"ok": False, "latency_ms": elapsed_ms, "status": e.code, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000)
        return {"ok": False, "latency_ms": elapsed_ms, "error": str(e)}
