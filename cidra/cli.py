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
    from cidra.integrations.llm import clear_latest_telemetry
    clear_latest_telemetry()  # telemetry is per run, not per process
    try:
        final_state = build_graph().invoke(state)
        outcome = final_state.get("outcome")
        log.info(f"Execution complete. Outcome: {outcome}")
        from cidra.integrations.llm import usage_summary
        used = usage_summary()
        log.info("LLM usage this run: %d requests, %d prompt + %d completion tokens",
                 used["requests"], used["prompt_tokens"], used["completion_tokens"])
        if outcome == "failed" and final_state.get("analysis_error"):
            log.error(f"Internal Error: {final_state.get('analysis_error')}")
        if final_state.get("comment_url"):
            log.info(f"Comment posted: {final_state.get('comment_url')}")
        if final_state.get("pr_url"):
            log.info(f"PR created: {final_state.get('pr_url')}")
        return final_state
    except Exception as e:
        log.exception("Graph execution failed")
        sys.exit(1)


def _lookup_pr(repo: str, branch: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Open PR for the failing branch, or (None, None). Never sinks the run."""
    if not branch:
        return None, None
    try:
        from cidra.integrations.github import open_pr_for_branch
        number = open_pr_for_branch(repo, branch)
    except Exception as e:  # noqa: BLE001 - a failed lookup means "no PR", not a crash
        log.warning("pull request lookup failed: %s", str(e)[:200])
        return None, None
    log.info("pull request for branch %s: %s", branch, number)
    return (number, branch) if number else (None, None)


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
    workflow_run = event_data.get("workflow_run") or {}
    target_run_id = str(workflow_run.get("id", run_id))
    # On workflow_run, GITHUB_SHA is the default branch's tip, not the commit
    # whose CI failed. The failing commit is head_sha; the workflow must check
    # that commit out (actions/checkout `ref:`) so it exists in the workspace.
    sha = workflow_run.get("head_sha") or sha

    # We might have an issue number if it's a pull_request
    issue_number = None
    pr_branch = None
    if "pull_request" in event_data:
        issue_number = event_data["pull_request"]["number"]
        pr_branch = event_data["pull_request"]["head"]["ref"]
    elif "workflow_run" in event_data and event_data["workflow_run"].get("pull_requests"):
        pr_data = event_data["workflow_run"]["pull_requests"][0]
        issue_number = pr_data["number"]
        pr_branch = pr_data["head"]["ref"]
    elif workflow_run:
        # The payload often lists no pull requests even when the commit has one.
        issue_number, pr_branch = _lookup_pr(repo, workflow_run.get("head_branch"))

    state = {
        "run_id": target_run_id,
        "repo": repo,
        "commit_sha": sha,
        "issue_number": issue_number,
        "pr_branch": pr_branch,
        "base_branch": workflow_run.get("head_branch"),
        # CIDRA_SOURCE_DIR: where the failing commit is checked out, when that
        # is not the workspace root (e.g. a second checkout in a subfolder).
        "source_dir": os.getenv("CIDRA_SOURCE_DIR") or os.getenv("GITHUB_WORKSPACE"),
        # The failing workflow's own file: its `env:` is replayed in the sandbox.
        "workflow_file": workflow_run.get("path"),
    }

    final = _run_graph(state)
    # A run where CIDRA itself broke (no log, no model, no sandbox) must not show
    # as a green job. diagnosis_only and flaky_detected are real results: exit 0.
    if final and final.get("outcome") == "failed":
        sys.exit(1)


def local_run(args):
    """Execution path for local developer usage."""
    log.info("Running in Local CLI mode")
    
    run_id = args.run_id or f"local-{uuid.uuid4().hex[:8]}"
    repo = args.repo or "local/dev"
    sha = args.sha or "HEAD"

    source = os.getcwd()
    raw_log = _sandbox_log(run_id, source, sha)

    state = {
        "run_id": run_id,
        "repo": repo,
        "commit_sha": sha,
        "source_dir": source,  # cloned at `sha` into a .git-free tree before any run
        "dry_run": True, # Don't try to post to GitHub
        "raw_log": raw_log, # Inject the local log directly to bypass GitHub API
    }

    _run_graph(state)


def _sandbox_log(run_id: str, source: str, sha: str) -> str:
    """The failure log for a local run, produced inside the sandbox.

    The repository's code never runs on this machine: the tests run against the
    same .git-free copy of `sha` the pipeline repairs, in a network-off container.
    Exits when there is nothing to fix or the sandbox cannot run.
    """
    from cidra.git_ops import git
    from cidra.nodes.checkout import prepare_checkout, remove_checkout
    from cidra.nodes.environment import sandbox_install_command, sandbox_test_command, workflow_python
    from cidra.sandbox.runner import Session

    try:
        if git("status", "--porcelain", cwd=source).stdout.strip():
            log.warning("Uncommitted changes are ignored: CIDRA tests the commit %s, not the working tree.", sha)
    except Exception:  # noqa: BLE001 - not a git checkout: prepare_checkout reports it
        pass
    log_run = f"{run_id}-log"
    try:
        tree = prepare_checkout(log_run, source, sha)
        log.info("Running the tests in the sandbox to get the failure log...")
        with Session(tree, workflow_python(tree)) as session:
            installed = session.install(sandbox_install_command({"source_dir": str(tree)}))
            if not installed.passed:
                log.error("Installing dependencies failed (set CIDRA_INSTALL_COMMAND):\n%s",
                          (installed.stdout_tail + installed.stderr_tail)[-2000:])
                sys.exit(1)
            result = session.run("test", sandbox_test_command({}))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - no Docker, no image, not a git repo
        log.error("Could not run the tests in the sandbox: %s", e)
        sys.exit(1)
    finally:
        remove_checkout(log_run)
    if result.passed:
        log.info("Tests pass in the sandbox. Nothing to fix.")
        sys.exit(0)
    log.info("Tests failed. CIDRA is stepping in to debug...")
    return result.stdout_tail + "\n" + result.stderr_tail


def verify_run(args) -> int:
    """`cidra verify`: rerun a fix's verification in the sandbox, the way the
    pipeline did (ROADMAP M2), so a reviewer can check a fix without trusting
    the report. The failing tests must fail before the patch, pass after it,
    and no test that passed may fail. Exit 0 when verified, 1 otherwise.
    """
    import pathlib
    from cidra.evidence import test_rows
    from cidra.nodes.checkout import prepare_checkout, remove_checkout
    from cidra.nodes.environment import close_session, install_deps, prepare_sandbox, session_for, workflow_python
    from cidra.nodes.fix import verify_fix
    from cidra.nodes.reproduce import reproduce_once

    patch = pathlib.Path(args.patch).read_text(encoding="utf-8")
    run_id = f"verify-{uuid.uuid4().hex[:8]}"
    state: dict = {"run_id": run_id, "install_command": args.install, "test_command": args.test,
                   "ci_failing_tests": args.target or []}
    try:
        tree = prepare_checkout(run_id, args.source, args.sha)
        state.update(source_dir=str(tree), python_version=workflow_python(tree))
        state.update(prepare_sandbox(state))
        if state.get("env_ready") is not False:
            state.update(install_deps(state))
        if state.get("env_ready") is False:
            print(f"Could not set up the sandbox: {state.get('analysis_error')}")
            return 1
        state.update(reproduce_once(state))
        if not state.get("reproduced"):
            print(f"Not reproduced, so there is nothing to verify: {state.get('analysis_error')}")
            return 1
        applied = session_for(run_id).apply_patch(patch)
        if not applied.passed:
            print(f"The patch does not apply to {args.sha}:\n{(applied.stdout_tail or applied.stderr_tail)[-1000:]}")
            return 1
        state.update(verify_fix({**state, "patch_applied": True}))
    except Exception as e:  # noqa: BLE001 - no Docker, no image, not a git repo
        print(f"Could not run the verification: {e}")
        return 1
    finally:
        close_session(run_id)
        remove_checkout(run_id)
    print("\n".join(test_rows(state)))
    print("\nVerified." if state.get("verified") else f"\nNot verified: {state.get('verify_note')}")
    return 0 if state.get("verified") else 1


def dashboard_run(args):
    """Start the CIDRA web dashboard and FastAPI backend."""
    import uvicorn
    import webbrowser
    port = getattr(args, "port", 8000)
    host = getattr(args, "host", "127.0.0.1")
    from cidra import config
    if host not in ("127.0.0.1", "localhost", "::1") and not config.DASHBOARD_TOKEN:
        log.error("Refusing to serve the dashboard on %s without CIDRA_DASHBOARD_TOKEN: "
                  "its API reads credentials and writes .env.", host)
        sys.exit(1)
    url = f"http://{host}:{port}"
    log.info(f"Starting CIDRA Web Dashboard at {url}")
    if not getattr(args, "no_open", False):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run("cidra.server.app:app", host=host, port=port, log_level="info")


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
    
    # 'verify' command: rerun a fix's verification, as printed in the report's evidence
    verify_parser = subparsers.add_parser("verify", help="Rerun the verification of a fix in the sandbox")
    verify_parser.add_argument("--patch", required=True, help="Diff file of the fix (e.g. `gh pr diff <n> > fix.diff`)")
    verify_parser.add_argument("--sha", default="HEAD", help="The failing commit the patch is made against")
    verify_parser.add_argument("--source", default=".", help="Path to the repository (default: current directory)")
    verify_parser.add_argument("--install", help="Install command (default: CIDRA_INSTALL_COMMAND)")
    verify_parser.add_argument("--test", help="Test command (default: CIDRA_TEST_COMMAND)")
    verify_parser.add_argument("--target", action="append", help="A test that must go from failing to passing (repeatable)")

    # 'dashboard' command for local web UI
    dash_parser = subparsers.add_parser("dashboard", help="Start the web dashboard & API server")
    dash_parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000)")
    dash_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    dash_parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    
    args = parser.parse_args()
    
    # Inside Actions a bare `cidra` is the Action; a named command still runs itself.
    if args.command == "action" or (args.command is None and os.getenv("GITHUB_ACTIONS") == "true"):
        action_run()
    elif args.command == "fix":
        local_run(args)
    elif args.command == "verify":
        sys.exit(verify_run(args))
    elif args.command == "dashboard":
        dashboard_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
