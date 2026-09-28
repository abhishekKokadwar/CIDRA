"""CIDRA Command Line Interface. Phase 12.

Entrypoint for both the GitHub Action and local developer runs.
"""

import argparse
import json
import logging
import os
import sys
import uuid
from typing import Optional

from cidra.graph import build_graph

log = logging.getLogger("cidra.cli")


def _setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("cidra").setLevel(logging.INFO)


def _run_graph(state: dict) -> dict:
    log.info("Starting CIDRA graph execution...")
    try:
        final_state = build_graph().invoke(state)
        outcome = final_state.get("outcome")
        log.info(f"Execution complete. Outcome: {outcome}")
        if final_state.get("comment_url"):
            log.info(f"Comment posted: {final_state.get('comment_url')}")
        if final_state.get("pr_url"):
            log.info(f"PR created: {final_state.get('pr_url')}")
        return final_state
    except Exception as e:
        log.exception("Graph execution failed")
        sys.exit(1)


def action_run():
    """Execution path when running inside a GitHub Action."""
    log.info("Running in GitHub Actions mode")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    sha = os.getenv("GITHUB_SHA")

    if not all([event_path, repo, run_id, sha]):
        log.error("Missing required GitHub Action environment variables.")
        sys.exit(1)

    try:
        with open(event_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)
    except Exception as e:
        log.error(f"Failed to read GitHub event payload: {e}")
        sys.exit(1)

    # If triggered by workflow_run, the failing run is in the payload.
    # Otherwise, it might be the current run.
    target_run_id = str(event_data.get("workflow_run", {}).get("id", run_id))
    
    # We might have an issue number if it's a pull_request
    issue_number = None
    if "pull_request" in event_data:
        issue_number = event_data["pull_request"]["number"]

    state = {
        "run_id": target_run_id,
        "repo": repo,
        "commit_sha": sha,
        "issue_number": issue_number,
    }
    
    _run_graph(state)


def local_run(args):
    """Execution path for local developer usage."""
    log.info("Running in Local CLI mode")
    
    run_id = args.run_id or f"local-{uuid.uuid4().hex[:8]}"
    repo = args.repo or "local/dev"
    sha = args.sha or "HEAD"

    state = {
        "run_id": run_id,
        "repo": repo,
        "commit_sha": sha,
        "source_dir": str(os.getcwd()), # Map current dir into sandbox
        "dry_run": True, # Don't try to post to GitHub
    }

    _run_graph(state)


def main():
    _setup_logging()
    
    parser = argparse.ArgumentParser(description="CIDRA - Autonomous CI Repair Agent")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # 'fix' command for local usage
    fix_parser = subparsers.add_parser("fix", help="Run CIDRA locally to fix the current project")
    fix_parser.add_argument("--repo", type=str, help="Repository name (e.g., owner/repo)")
    fix_parser.add_argument("--sha", type=str, help="Commit SHA")
    fix_parser.add_argument("--run-id", type=str, help="Optional run ID")
    
    # 'action' command for GitHub Actions
    subparsers.add_parser("action", help="Run CIDRA as a GitHub Action (relies on env vars)")
    
    args = parser.parse_args()
    
    if os.getenv("GITHUB_ACTIONS") == "true" or args.command == "action":
        action_run()
    elif args.command == "fix":
        local_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
