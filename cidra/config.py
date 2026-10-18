"""All bounds and limits in one place. See docs/4_architecture.md §4.4."""

import os

from dotenv import load_dotenv

# The project's .env: in the directory CIDRA runs from, where the dashboard's
# Settings page saves it too. Not next to the installed package, which after
# a pip install is site-packages.
ENV_FILE = os.environ.get("CIDRA_ENV_FILE") or ".env"
load_dotenv(ENV_FILE)

# Bounded loops
MAX_ANALYSIS_ATTEMPTS = 2
MAX_FIX_ATTEMPTS = 3
FLAKY_RUNS = 5
# A test is flagged FLAKY when its Deterministic Flakiness Score (0-100, see
# reproduce.flakiness_score) is at or above this. 1 means "any disagreement
# across runs is flaky" — the strict reading, since a repair loop against a
# non-deterministic test is meaningless (2_scope_and_decisions.md §2).
FLAKY_SCORE_THRESHOLD = 1

# Provider — any OpenAI-compatible endpoint, one key (BYOK).
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
API_KEY = os.environ.get("CIDRA_API_KEY", "")
BASE_URL = os.environ.get("CIDRA_BASE_URL") or GEMINI_BASE_URL

# One optional fallback, tried only when the primary call fails: Gemini, through
# its OpenAI-compatible endpoint. No GEMINI_API_KEY, no fallback.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FALLBACK_MODEL = os.environ.get("CIDRA_FALLBACK_MODEL") or "gemini-3.5-flash"

# Models — cheap for classification, stronger for code edits.
# See docs/5_fixtures.md §6: record which model produced each eval row.
# Defaults match the default BASE_URL (Gemini). `or`, not a get() default: the
# GitHub Action passes an empty string when the input is unset.
# Per-run spend caps. One run normally makes 2 requests (analyze, fix) and at most
# 5 (2 analyses + 3 fix attempts); retries and fallbacks draw from the same
# allowance. Past either cap the run stops asking and reports what it has.
MAX_LLM_CALLS = int(os.environ.get("CIDRA_MAX_LLM_CALLS") or 8)
MAX_LLM_TOKENS = int(os.environ.get("CIDRA_MAX_LLM_TOKENS") or 40000)

# Your price per million prompt / completion tokens, for the cost line of a report.
# Unset: CIDRA uses a list price only for models it knows (integrations/llm.py).
PRICE_IN = float(os.environ["CIDRA_PRICE_IN"]) if os.environ.get("CIDRA_PRICE_IN") else None
PRICE_OUT = float(os.environ["CIDRA_PRICE_OUT"]) if os.environ.get("CIDRA_PRICE_OUT") else None

MODEL_ANALYZE = os.environ.get("CIDRA_MODEL_ANALYZE") or "gemini-3.5-flash"
MODEL_FIX = os.environ.get("CIDRA_MODEL_FIX") or "gemini-3.5-flash"

# GitHub, fine-grained PATs scoped to the practice repo.
# Reads prefer the read-only token: a token that cannot write cannot be made
# to write by a prompt injection in a CI log. GITHUB_TOKEN (Contents:rw,
# PRs:rw) is only for code that deliberately mutates the repo — Phase 6.
GITHUB_TOKEN = os.environ.get("CIDRA_GITHUB_TOKEN", "")
GITHUB_TOKEN_RO = os.environ.get("CIDRA_GITHUB_TOKEN_RO", "") or GITHUB_TOKEN
GITHUB_API = os.environ.get("CIDRA_GITHUB_API", "https://api.github.com")

# Shared secret for GitHub webhook HMAC-SHA256 verification (Phase 7). Set the
# same value in the repo's webhook config. An unsigned request is rejected, so a
# missing secret means CIDRA refuses every delivery rather than trusting it.
WEBHOOK_SECRET = os.environ.get("CIDRA_WEBHOOK_SECRET", "")

# Dashboard API token. Optional on loopback (the API then only answers same-origin
# requests); REQUIRED to serve the dashboard on any other interface. Clients send
# it as the X-CIDRA-Token header.
DASHBOARD_TOKEN = os.environ.get("CIDRA_DASHBOARD_TOKEN", "")

# Idempotency store location.
IDEMPOTENCY_DB = os.environ.get("CIDRA_IDEMPOTENCY_DB", "cidra_idempotency.db")

# Local repo used for fixture runs until the live webhook clones a real one.
PRACTICE_REPO_DIR = os.environ.get("CIDRA_PRACTICE_REPO", "d:/CODES/cidra-practice")

# Where per-run isolated checkouts live (Phase 9). One dir per run_id so
# concurrent repairs never collide on a shared working tree.
WORKTREE_ROOT = os.environ.get("CIDRA_WORKTREE_ROOT", "worktrees")

# Fix cache (Phase 11): verified fixes keyed by failure fingerprint, so an
# identical failure reuses the fix instead of paying for the LLM again.
FIX_CACHE_PATH = os.environ.get("CIDRA_FIX_CACHE", "cidra_fix_cache.json")

# Run history (Phase 13): one compact JSON summary per finished run, appended so
# the Fleet TUI / dashboard can show what CIDRA has done.
RUN_HISTORY_PATH = os.environ.get("CIDRA_RUN_HISTORY", "cidra_run_history.jsonl")

# Install and test commands. Set by whoever operates CIDRA (these variables, or
# per run through the state); never assembled from LLM output or repo content.
# The install command must be a `pip install ...`: the sandbox appends --target.
# Unset: chosen per repository from the files it has (environment.detect_install).
INSTALL_COMMAND = os.environ.get("CIDRA_INSTALL_COMMAND") or None
TEST_COMMAND = os.environ.get("CIDRA_TEST_COMMAND") or "pytest -q 2>&1"

# Log isolation windows (lines around an error marker)
LOG_LINES_BEFORE = 30
LOG_LINES_AFTER = 60

ERROR_MARKERS = (
    "##[error]",  # GitHub's own annotation — the most reliable anchor in a CI log
    "Traceback",
    "ModuleNotFoundError",
    "ImportError",
    "AssertionError",
    "FAILED",
    "Error:",
    "Exception",
    "KeyError",
)

# Output safety — disable PR creation by default until the workflow is verified safe
# (Phase 9.6 / GitHub Action Release Phase)
ENABLE_PR_CREATION = os.environ.get("CIDRA_ENABLE_PR_CREATION", "false").lower() == "true"

# Air-gapped / on-premise execution flag
AIR_GAPPED = os.environ.get("CIDRA_AIR_GAPPED", "false").lower() == "true"
