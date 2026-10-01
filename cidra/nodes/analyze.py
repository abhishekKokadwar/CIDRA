"""Root-cause analysis. See docs/4_architecture.md §5 nodes 3-4.

Two nodes so a bad LLM response is a retryable state, not an exception:
analyze calls the model, validate_analysis decides whether to trust it.
"""

from cidra import config
from cidra.integrations.llm import structured
from cidra.state import Analysis, DebugState

SYSTEM = """You classify Python CI failures into exactly one category.

Categories:
- missing_dependency: an import fails because a package is not installed or not declared.
  Set missing_package (see the naming rule below).
- assertion_error: an assert compared two values and the log PRINTS BOTH of them, so
  the correct result is stated rather than inferred (e.g. "assert [1, 3] == [1, 3, 6]"
  or "assert 4 == 5"). The gap between the two sides is the whole diagnosis.
- env_config_error: a required environment variable is absent, empty, or malformed.
  Set env_var to its name.
- flaky_test: the failure depends on timing, randomness, ordering, or concurrency —
  the same commit would pass on a rerun.
- unknown: anything else. Choose it when the log does not show you what the correct
  behaviour should be — a wrong condition, a missing branch, an unhandled case, or an
  exception escaping application code rather than a failed assert. If fixing it means
  deciding intent that the log never states, it is unknown.

Rules:
- Prefer unknown whenever you are not certain. A confident wrong answer is far worse
  than admitting the failure is out of scope: a wrong category causes an automated
  patch to be written against a misunderstanding.
- Never choose assertion_error just because pytest reported a test failure. An
  exception raised inside application code is not an assertion_error even when it
  fails a test — no expected value was printed, so nothing tells you the right answer.
- Report only what the log shows. Never invent a file, package, or test name.
- failing_test must be the full pytest node id, path included, exactly as it
  appears in the log: "tests/test_x.py::test_name". Never the bare function name.
- For missing_dependency, missing_package must be the INSTALLABLE distribution name,
  which sometimes differs from the imported module ("yaml" installs as "pyyaml",
  "cv2" as "opencv-python"). Give the name that belongs in requirements.txt.
- Leave file null when the log gives no evidence for the path that needs editing.
  A guess is worse than an omission; the fix step knows the conventional locations.

Setting `file` — the file a human would EDIT, which is usually not the file in the
traceback. Only set it when the log actually supports it:
- wrong value produced by application code -> the source file computing it, not the
  test that asserted on it
- a test encoding a genuinely wrong expectation -> that test file
- undeclared dependency or missing CI env var -> leave null; the fix step knows the
  manifest and workflow paths, and the log does not show them

confidence is your genuine certainty, not a score to maximise."""


def analyze_region(error_region: str) -> Analysis:
    """The LLM call itself. Separated so eval Tier 2 can call it without a graph."""
    return structured(
        model=config.MODEL_ANALYZE,  # read at call time: the settings API can change it
        schema=Analysis,
        system=SYSTEM,
        user=f"Classify this CI failure.\n\n<log>\n{error_region}\n</log>",
        max_tokens=600,  # an Analysis is ~150 tokens; the cap reserves credit up front
    )


def analyze(state: DebugState) -> dict:
    attempts = state.get("analysis_attempts", 0) + 1
    try:
        analysis = analyze_region(state.get("error_region", ""))
    except Exception as e:  # network, rate limit, or ValidationError on a bad shape
        # Any failure is retryable state; route_after_validate enforces the bound.
        return {"analysis_attempts": attempts, "analysis": None, "analysis_error": str(e)[:500]}
    return {"analysis_attempts": attempts, "analysis": analysis, "analysis_error": None}


def validate_analysis(state: DebugState) -> dict:
    """Reject an analysis that is structurally valid but unusable, and enforce enterprise policy."""
    analysis = state.get("analysis")
    if analysis is None:
        return {}
    if analysis.category == "missing_dependency" and not analysis.missing_package:
        return {"analysis": None, "analysis_error": "missing_dependency without missing_package"}
    if analysis.category == "env_config_error" and not analysis.env_var:
        return {"analysis": None, "analysis_error": "env_config_error without env_var"}

    from cidra.policy import PolicyEngine, PolicyDecision
    source_dir = state.get("source_dir")
    policy_engine = PolicyEngine.find_and_load(source_dir)
    decision, reason = policy_engine.evaluate_category(analysis.category)

    updates: dict = {
        "policy_decision": decision.value,
        "policy_reasons": [reason],
        "policy_sha256": policy_engine.policy_sha256,
        "requires_human_approval": decision == PolicyDecision.REQUIRE_HUMAN_APPROVAL,
    }

    if decision == PolicyDecision.STRICT_REFUSAL:
        updates["outcome"] = "diagnosis_only"

    return updates
