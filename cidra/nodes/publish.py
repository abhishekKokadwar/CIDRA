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

    out: dict = {"final_output": body, "comment_url": None, "pr_url": None, "publish_errors": []}
    if dry:
        return out
    from cidra.integrations import github_write
    errors = out["publish_errors"]

    # Draft PR for a verified fix (Phase 9.6).
    from cidra.config import ENABLE_PR_CREATION
    if ENABLE_PR_CREATION and state.get("outcome") == "verified_fix" and state.get("fix_diff"):
        if state.get("issue_number") and state.get("pr_branch"):
            # Failure on a pull request: push the fix to it and comment there.
            out["pr_url"] = _attempt(errors, "update the pull request", "contents: write, pull-requests: write",
                                     _apply_to_existing_pr, state, body)
        else:
            # Failure on a push: open a new draft PR.
            out["pr_url"] = _attempt(errors, "open a draft pull request", "contents: write, pull-requests: write",
                                     _open_pr, state, body)
    if out["pr_url"] is None:
        # No PR, or the PR step failed: the report must still be posted somewhere.
        if issue is not None:
            out["comment_url"] = _attempt(errors, "comment on the pull request", "pull-requests: write",
                                          github_write.post_or_update_comment, state["repo"], issue, body)
        elif state.get("commit_sha") and state.get("commit_sha") != "HEAD":
            out["comment_url"] = _attempt(errors, "comment on the commit", "contents: write",
                                          github_write.post_or_update_commit_comment,
                                          state["repo"], state["commit_sha"], body)
    if errors:
        _write_job_summary("\n".join(f"> **CIDRA could not publish:** {e}" for e in errors))
    return out


def _attempt(errors: list, what: str, permissions: str, fn, *args):
    """One GitHub write. A failure is recorded, not raised: the report is already
    in the job summary, and the run must still clean up. A 403 names the missing
    workflow permission, the usual cause on a first install."""
    import logging
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - every write failure is reported the same way
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 403:
            msg = (f"GitHub refused to {what} (403). Give the workflow job that runs CIDRA "
                   f"`permissions:` {permissions}.")
        else:
            msg = f"could not {what}: {str(e)[:200]}"
        logging.getLogger("cidra.publish").error(msg)
        errors.append(msg)
        return None


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
    """Build the fix branch and open a draft PR. Returns its URL; raises on error (publish records it)."""
    from cidra.config import GITHUB_API, GITHUB_TOKEN
    from cidra.integrations.github_write import open_draft_pr
    from cidra.nodes.pr import build_fix_branch

    run_id = state["run_id"]
    repo = state["repo"]
    # Keyed by the failing commit, not the CI run: a commit usually has two runs
    # (push and pull_request), and both must land on one branch and one PR.
    key = (state.get("commit_sha") or run_id)[:12]
    branch = build_fix_branch(
        key, _repo_dir(state), state["fix_diff"], repo, GITHUB_TOKEN, GITHUB_API,
        base_sha=state.get("commit_sha"),
    )
    return open_draft_pr(
        repo, branch,
        title=f"CIDRA: verified fix for {state.get('commit_sha', run_id)[:12]}",
        body=body,
        # Target the branch whose CI failed. Against the default branch the PR
        # would carry the breaking commit too, and can net out to an empty diff.
        base=state.get("base_branch"),
    )


def _apply_to_existing_pr(state: DebugState, body: str) -> Optional[str]:
    """Build and push the fix branch to the existing PR, and post a comment."""
    from cidra.config import GITHUB_API, GITHUB_TOKEN
    from cidra.nodes.pr import build_fix_branch
    from cidra.integrations.github_write import post_or_update_comment

    run_id = state["run_id"]
    repo = state["repo"]
    # Push to the existing PR branch, then comment on the PR.
    build_fix_branch(
        run_id, _repo_dir(state), state["fix_diff"], repo, GITHUB_TOKEN, GITHUB_API,
        base_sha=state.get("commit_sha"),
        branch_name=state["pr_branch"]
    )
    return post_or_update_comment(repo, state["issue_number"], body)


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
    from cidra.nodes.checkout import source_run_id
    remove_checkout(source_run_id(run_id))  # the fetched source, in webhook mode
    record(state)  # Phase 13: append this run to the history (best-effort)
    return {}
