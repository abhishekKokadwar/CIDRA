"""State object flowing through the graph. See docs/4_architecture.md §3."""

from typing import TypedDict, Literal, Optional

from pydantic import BaseModel, Field

FailureCategory = Literal[
    "missing_dependency",  # rank 1
    "assertion_error",  # rank 2
    "env_config_error",  # rank 3
    "flaky_test",  # rank 4 — distinct path, see docs/4_architecture.md §4.3
    "unknown",  # out of scope or analysis failed
]

Outcome = Literal[
    "verified_fix",
    "flaky_detected",
    "diagnosis_only",
    "failed",
]

Step = Literal["checkout", "install", "test", "verify"]


class Analysis(BaseModel):
    """LLM output. `category` routes the graph."""

    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    proposed_action: str
    file: Optional[str] = None
    line: Optional[int] = None
    failing_test: Optional[str] = None
    missing_package: Optional[str] = None  # rank-1 only
    env_var: Optional[str] = None  # rank-3 only


class SandboxResult(BaseModel):
    """One container execution."""

    step: Step
    exit_code: int
    stdout_tail: str
    stderr_tail: str
    duration_s: float
    timed_out: bool

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class DebugState(TypedDict, total=False):
    # Identity — written by entrypoint
    run_id: str
    repo: str
    commit_sha: str
    workflow_file: Optional[str]
    source_dir: Optional[str]  # host checkout copied into the sandbox
    ci_env: dict  # env the workflow sets; replicated in the sandbox

    # Ingestion
    raw_log: str  # never sent to the LLM
    error_region: str
    log_markers: list[str]

    # Analysis
    analysis: Optional[Analysis]
    analysis_attempts: int
    analysis_error: Optional[str]

    # Environment
    image_tag: Optional[str]
    env_ready: bool

    # Reproduction
    reproduced: bool
    repro_results: list[SandboxResult]
    flaky_pass_count: Optional[int]

    # Fix + verify
    fix_strategy: Optional[str]
    fix_diff: Optional[str]
    fix_attempts: int
    patch_applied: bool
    verified: bool  # written by verify_fix ONLY
    verify_results: list[SandboxResult]

    # Terminal
    outcome: Outcome
    final_output: str
    comment_url: Optional[str]
