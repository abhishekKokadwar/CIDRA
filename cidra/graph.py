"""Graph assembly. See docs/4_architecture.md §4.

Nodes are stubs until their phase fills them in; the topology is real from Phase 0
so later phases only add bodies, never rewiring.
"""

from langgraph.graph import StateGraph, START, END

from cidra import routers
from cidra.nodes import audit, environment, fix, ingest, localize, publish, reproduce
from cidra.nodes.analyze import analyze, validate_analysis
from cidra.state import DebugState


def _passthrough(name: str):
    """Stub node: records that it ran. Replaced phase by phase."""

    def node(state: DebugState) -> dict:
        return {"log_markers": [*state.get("log_markers", []), name]}

    return node


def build_graph():
    g = StateGraph(DebugState)

    g.add_node("fetch_log", ingest.fetch_log)
    g.add_node("isolate_error", ingest.isolate_error)
    g.add_node("analyze", analyze)
    g.add_node("validate_analysis", validate_analysis)
    g.add_node("prepare_sandbox", environment.prepare_sandbox)
    g.add_node("checkout_commit", environment.checkout_commit)
    g.add_node("install_deps", environment.install_deps)
    g.add_node("route_category", _passthrough("route_category"))
    g.add_node("reproduce_once", reproduce.reproduce_once)
    g.add_node("reproduce_n_times", reproduce.reproduce_n_times)
    g.add_node("classify_flakiness", reproduce.classify_flakiness)
    g.add_node("localize", localize.localize)
    g.add_node("select_strategy", fix.select_strategy)
    g.add_node("generate_fix", fix.generate_fix)
    g.add_node("audit_patch", audit.audit_patch)
    g.add_node("apply_patch", fix.apply_patch)
    g.add_node("verify_fix", fix.verify_fix)
    g.add_node("compose_report", publish.compose_report)
    g.add_node("publish", publish.publish)
    g.add_node("cleanup", publish.cleanup)

    g.add_edge(START, "fetch_log")
    g.add_edge("fetch_log", "isolate_error")
    g.add_edge("isolate_error", "analyze")
    g.add_edge("analyze", "validate_analysis")
    g.add_conditional_edges(
        "validate_analysis",
        routers.route_after_validate,
        ["analyze", "checkout_commit", "compose_report"],
    )
    g.add_edge("checkout_commit", "prepare_sandbox")
    g.add_edge("prepare_sandbox", "install_deps")
    g.add_conditional_edges(
        "install_deps",
        routers.route_after_env,
        ["route_category", "compose_report"],
    )
    g.add_conditional_edges(
        "route_category",
        routers.route_category,
        ["reproduce_once", "reproduce_n_times"],
    )
    g.add_edge("reproduce_n_times", "classify_flakiness")
    g.add_conditional_edges(
        "classify_flakiness",
        routers.route_after_flaky,
        ["reproduce_once", "compose_report"],
    )
    g.add_conditional_edges(
        "reproduce_once",
        routers.route_after_reproduce,
        ["localize", "compose_report"],
    )
    g.add_edge("localize", "select_strategy")
    g.add_conditional_edges(
        "select_strategy",
        routers.route_after_strategy,
        ["generate_fix", "audit_patch", "compose_report"],
    )
    g.add_edge("generate_fix", "audit_patch")
    g.add_conditional_edges(
        "audit_patch",
        routers.route_after_audit,
        ["apply_patch", "compose_report"],
    )
    g.add_edge("apply_patch", "verify_fix")
    g.add_conditional_edges(
        "verify_fix",
        routers.route_after_verify,
        ["generate_fix", "compose_report"],
    )
    g.add_edge("compose_report", "publish")
    g.add_edge("publish", "cleanup")
    g.add_edge("cleanup", END)

    return g.compile()
