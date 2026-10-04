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
    repo_dir: Optional[str]  # the original repo WITH .git; the PR path clones this
    base_branch: Optional[str]  # branch whose CI failed; a new fix PR targets it
    ci_env: dict  # env the workflow sets; replicated in the sandbox

    # Ingestion
    raw_log: str  # never sent to the LLM
    error_region: str
    log_markers: list[str]
    fingerprint: str  # stable hash of the failure (Phase 11)
    cache_hit: bool  # a verified fix for this fingerprint was reused (0 LLM calls)

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
    flaky_score: Optional[int]  # 0-100 Deterministic Flakiness Score (Phase 8)

    # Fault localization (Phase 8, SBFL)
    sbfl_ranking: list[str]  # top suspicious elements, most-first
    sbfl_evidence: str  # prompt-ready block; fed to the fix step as structured evidence

    # Fix + verify
    fix_strategy: Optional[str]
    fix_diff: Optional[str]
    fix_attempts: int
    patch_audit_ok: bool  # written by audit_patch (Phase 10); gates apply_patch
    patch_audit_reasons: list[str]  # SR-13/14/15 violations, if rejected
    patch_surfaced: list[str]  # dependency-pin changes to show the reviewer
    patch_applied: bool
    apply_error: Optional[str]  # why the last diff did not apply; fed to the next attempt
    verified: bool  # written by verify_fix ONLY
    verify_results: list[SandboxResult]

    # Output target (set by the webhook in Phase 7; absent for fixture runs)
    issue_number: Optional[int]  # PR/issue to comment on
    dry_run: bool  # render but do not post — default when identity/token missing

    # Enterprise Security & Policy
    policy_decision: Optional[str]  # auto_remediate, require_human_approval, strict_refusal
    policy_reasons: Optional[list[str]]
    policy_sha256: Optional[str]
    requires_human_approval: bool
    audit_manifest: Optional[dict]

    # Terminal
    outcome: Outcome
    final_output: str
    comment_url: Optional[str]
    pr_url: Optional[str]  # draft PR for a verified fix (Phase 9.6)
