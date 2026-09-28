"""All bounds and limits in one place. See docs/4_architecture.md §4.4."""

import os

from dotenv import load_dotenv

load_dotenv()

# Bounded loops
MAX_ANALYSIS_ATTEMPTS = 2
MAX_FIX_ATTEMPTS = 3
FLAKY_RUNS = 5
# A test is flagged FLAKY when its Deterministic Flakiness Score (0-100, see
# reproduce.flakiness_score) is at or above this. 1 means "any disagreement
# across runs is flaky" — the strict reading, since a repair loop against a
# non-deterministic test is meaningless (2_scope_and_decisions.md §2).
FLAKY_SCORE_THRESHOLD = 1

# Provider — any OpenAI-compatible endpoint. OpenRouter for now.
API_KEY = os.environ.get("CIDRA_API_KEY", "")
BASE_URL = os.environ.get("CIDRA_BASE_URL", "https://openrouter.ai/api/v1")

# NVIDIA Fallback
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Models — cheap for classification, stronger for code edits.
# See docs/5_fixtures.md §6: record which model produced each eval row.
MODEL_ANALYZE = os.environ.get("CIDRA_MODEL_ANALYZE", "anthropic/claude-haiku-4.5")
MODEL_FIX = os.environ.get("CIDRA_MODEL_FIX", "anthropic/claude-sonnet-4.5")

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

# Test command. CIDRA-authored and fixed — never assembled from LLM output.
TEST_COMMAND = "python -m pytest -q 2>&1"

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
