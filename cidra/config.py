"""All bounds and limits in one place. See docs/4_architecture.md §4.4."""

import os

from dotenv import load_dotenv

load_dotenv()

# Bounded loops
MAX_ANALYSIS_ATTEMPTS = 2
MAX_FIX_ATTEMPTS = 3
FLAKY_RUNS = 5

# Provider — any OpenAI-compatible endpoint. OpenRouter for now.
API_KEY = os.environ.get("CIDRA_API_KEY", "")
BASE_URL = os.environ.get("CIDRA_BASE_URL", "https://openrouter.ai/api/v1")

# Models — cheap for classification, stronger for code edits.
# See docs/5_fixtures.md §6: record which model produced each eval row.
MODEL_ANALYZE = os.environ.get("CIDRA_MODEL_ANALYZE", "anthropic/claude-haiku-4.5")
MODEL_FIX = os.environ.get("CIDRA_MODEL_FIX", "anthropic/claude-sonnet-4.5")

# GitHub. Read-only fine-grained PAT: Actions:read + Contents:read.
GITHUB_TOKEN = os.environ.get("CIDRA_GITHUB_TOKEN", "")
GITHUB_API = os.environ.get("CIDRA_GITHUB_API", "https://api.github.com")

# Local repo used for fixture runs until the live webhook clones a real one.
PRACTICE_REPO_DIR = os.environ.get("CIDRA_PRACTICE_REPO", "d:/CODES/cidra-practice")

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
