"""Output. See docs/4_architecture.md §5 nodes 16-18. Phase 6."""

from typing import Optional

from cidra.state import DebugState


def compose_report(state: DebugState) -> dict:
    """Pure. Never claims a fix that wasn't verified."""
    if state.get("outcome"):
        outcome = state["outcome"]
    elif state.get("verified"):
        outcome = "verified_fix"
    elif state.get("analysis") is None:
        outcome = "failed"
    elif not state.get("reproduced"):
        outcome = "failed"
    else:
        outcome = "diagnosis_only"

    # Enterprise Policy & Cryptographic Audit Manifest
    from cidra.policy import PolicyEngine
    from cidra.audit_manifest import generate_manifest

    pe = PolicyEngine.find_and_load(state.get("source_dir"))
    manifest = generate_manifest(state, pe)
    manifest_dict = manifest.to_dict()

    return {
        "outcome": outcome,
        "audit_manifest": manifest_dict,
        "policy_decision": manifest.policy.decision,
        "policy_reasons": manifest.policy.reasons,
        "policy_sha256": manifest.policy.sha256,
    }


def publish(state: DebugState) -> dict:
    """Render the report, persist audit manifest, and post as comment. Phase 6, step 6.3."""
    import json
    from pathlib import Path
    from cidra.config import GITHUB_TOKEN
    from cidra.nodes.report import render_comment

    # Save cryptographic audit manifest to disk
    manifest_dict = state.get("audit_manifest")
    if manifest_dict:
        try:
            manifest_file = Path("cidra_audit_manifest.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest_dict, f, indent=2)
        except Exception:
            pass

    body = render_comment(state)
    _write_job_summary(body)
    issue = state.get("issue_number")
    has_token = bool(GITHUB_TOKEN)
    dry = state.get("dry_run") or not has_token

    out: dict = {"final_output": body, "comment_url": None, "pr_url": None}

    # Draft PR for a verified fix (Phase 9.6).
    from cidra.config import ENABLE_PR_CREATION
    if not dry and ENABLE_PR_CREATION and state.get("outcome") == "verified_fix" and state.get("fix_diff"):
        if state.get("issue_number") and state.get("pr_branch"):
            # Where did failure originate? -> Existing PR -> Update/fix THAT PR
            out["pr_url"] = _apply_to_existing_pr(state, body)
        else:
            # Where did failure originate? -> main push -> Open new PR
            out["pr_url"] = _open_pr(state, body)
        if out["pr_url"] is None and issue is not None:
            # The PR step failed: a verified fix must still be reported somewhere.
            from cidra.integrations.github_write import post_or_update_comment
            out["comment_url"] = post_or_update_comment(state["repo"], issue, body)
    else:
        # Refused or Failed (or dry run) -> Comment on existing PR
        if not dry and issue is not None:
            from cidra.integrations.github_write import post_or_update_comment
            out["comment_url"] = post_or_update_comment(state["repo"], issue, body)

    return out


def _write_job_summary(body: str) -> None:
    """Every Actions run leaves its report on the run page, whatever the outcome.

    A failure on a branch push has no PR to comment on, so without this a
    diagnosis-only or failed run is visible nowhere but the raw log.
    """
    import os
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(body + "\n")
    except OSError:
        pass  # best-effort: never sink the run over a summary


def _repo_dir(state: DebugState) -> str:
    """The repo to branch from. NOT source_dir: after checkout_commit that is the
    sandbox tree, which has no .git and cannot be cloned."""
    from cidra.config import PRACTICE_REPO_DIR
    return state.get("repo_dir") or state.get("source_dir") or PRACTICE_REPO_DIR


def _open_pr(state: DebugState, body: str) -> Optional[str]:
    """Build the fix branch and open a draft PR. Returns its URL, or None on error."""
    from cidra.config import GITHUB_API, GITHUB_TOKEN
    from cidra.integrations.github_write import open_draft_pr
    from cidra.nodes.pr import build_fix_branch, fix_branch_name

    run_id = state["run_id"]
    repo = state["repo"]
    try:
        branch = build_fix_branch(
            run_id, _repo_dir(state), state["fix_diff"], repo, GITHUB_TOKEN, GITHUB_API,
            base_sha=state.get("commit_sha"),
        )
        return open_draft_pr(
            repo, fix_branch_name(run_id),
            title=f"CIDRA: verified fix for {state.get('commit_sha', run_id)[:12]}",
            body=body,
            # Target the branch whose CI failed. Against the default branch the PR
            # would carry the breaking commit too, and can net out to an empty diff.
            base=state.get("base_branch"),
        )
    except Exception:  # noqa: BLE001 - a PR failure must not sink the comment
        import logging
        logging.getLogger("cidra.publish").exception("draft PR failed run_id=%s", run_id)
        return None


def _apply_to_existing_pr(state: DebugState, body: str) -> Optional[str]:
    """Build and push the fix branch to the existing PR, and post a comment."""
    from cidra.config import GITHUB_API, GITHUB_TOKEN
    from cidra.nodes.pr import build_fix_branch
    from cidra.integrations.github_write import post_or_update_comment

    run_id = state["run_id"]
    repo = state["repo"]
    try:
        # Push to the existing PR branch
        build_fix_branch(
            run_id, _repo_dir(state), state["fix_diff"], repo, GITHUB_TOKEN, GITHUB_API,
            base_sha=state.get("commit_sha"),
            branch_name=state["pr_branch"]
        )
        # Add a comment to the PR notifying them of the fix
        return post_or_update_comment(repo, state["issue_number"], body)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("cidra.publish").exception("apply to existing PR failed run_id=%s", run_id)
        return None


def cleanup(state: DebugState) -> dict:
    """Runs on every terminal path. Destroys the container.

    Every route to END passes through here (arch §4), so this is the one place
    that guarantees no container outlives a run.
    """
    from cidra.history import record
    from cidra.nodes.checkout import remove_checkout
    from cidra.nodes.environment import close_session

    run_id = state.get("run_id", "")
    close_session(run_id)
    remove_checkout(run_id)  # Phase 9: drop the per-run isolated checkout dir
    record(state)  # Phase 13: append this run to the history (best-effort)
    return {}
