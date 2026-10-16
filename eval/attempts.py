"""Every fix attempt of a run, rebuilt from the pipeline's step-by-step updates.

The final state keeps only the last diff, so a run that failed three attempts
says nothing about why. Streaming the graph gives each node's update in order;
this turns them into one record per attempt. Pure: no graph, no sandbox.
"""

# Why an attempt did not verify, most specific first. "verified" is the only success.
RESULTS = ("verified", "model_error", "empty_patch", "refused_by_audit", "did_not_apply",
           "regression", "still_failing", "did_not_complete")


def _result(a: dict) -> str:
    if a.get("verified"):
        return "verified"
    if a.get("model_error"):
        return "model_error"
    if not a.get("diff"):
        return "did_not_apply" if a.get("apply_error") else "empty_patch"
    if a.get("audit_ok") is False:
        return "refused_by_audit"
    if a.get("applied") is False:
        return "did_not_apply"
    if a.get("regressions"):
        return "regression"
    if a.get("still_failing"):
        return "still_failing"
    return "did_not_complete"


def attempts_from_updates(updates: list[tuple[str, dict]]) -> list[dict]:
    """One dict per fix attempt: the diff, what the gates said, and why it did or did not verify."""
    attempts: list[dict] = []
    for node, update in updates:
        update = update or {}
        if node == "select_strategy" and update.get("cache_hit"):
            attempts.append({"n": len(attempts) + 1, "source": "cache", "diff": update.get("fix_diff")})
        elif node == "generate_fix":
            attempts.append({"n": len(attempts) + 1, "source": "model", "diff": update.get("fix_diff"),
                             "model_error": update.get("analysis_error")})
            if update.get("apply_error"):  # edits that could not be placed in the file
                attempts[-1].update(applied=False, apply_error=update["apply_error"])
        elif attempts and node == "audit_patch":
            attempts[-1].update(audit_ok=update.get("patch_audit_ok"),
                                audit_reasons=update.get("patch_audit_reasons") or [])
        elif attempts and node == "apply_patch":
            # Without a diff apply_patch sends no apply_error: keep generate_fix's.
            attempts[-1].update({to: update[key] for key, to in
                                 (("patch_applied", "applied"), ("apply_error", "apply_error")) if key in update})
        elif attempts and node == "verify_fix":
            attempts[-1].update(verified=bool(update.get("verified")),
                                still_failing=update.get("verify_failing_tests") or [],
                                regressions=update.get("regressions") or [],
                                verify_note=update.get("verify_note"))
    for a in attempts:
        a["result"] = _result(a)
        if not a.get("model_error"):
            a.pop("model_error", None)
    return attempts


def why_not_verified(records: list[dict]) -> dict[str, int]:
    """How many attempts ended each way, over all runs."""
    counts = {r: 0 for r in RESULTS}
    for record in records:
        for a in record.get("attempts") or []:
            counts[a["result"]] += 1
    return {k: v for k, v in counts.items() if v}
