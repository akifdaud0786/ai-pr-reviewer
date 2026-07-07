"""
LangGraph workflow for the "AI AGENTS -- PARALLEL EXECUTION" stage of the pipeline.

Graph shape:

    load_repo_patterns
            |
            v
    ┌───────┴────────┬────────────┬───────────────┐
    v                v            v                v
static_analysis   security      style        architecture      (run concurrently)
    └───────┬────────┴────────────┴───────────────┘
            v
      merge_findings
            v
   remove_duplicates_and_summarize
            v
           END

Each agent node reads the shared `diff` + `repo_patterns` from graph state and
writes its own findings key, so the four branches never write-conflict with
each other. The merge node fans back in once all four have completed.
"""
from __future__ import annotations
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from orchestrator_service.agents import static_analysis, security, style, architecture
from orchestrator_service.agents.merge import merge_and_dedupe, build_summary


class ReviewState(TypedDict, total=False):
    repo_full_name: str
    pr_number: int
    diff: str
    repo_patterns: list[dict]

    static_analysis_findings: list[dict]
    security_findings: list[dict]
    style_findings: list[dict]
    architecture_findings: list[dict]

    merged_findings: list[dict]
    summary: str


async def _node_static_analysis(state: ReviewState) -> dict:
    findings = await static_analysis.run(state["diff"], state.get("repo_patterns", []))
    return {"static_analysis_findings": findings}


async def _node_security(state: ReviewState) -> dict:
    findings = await security.run(state["diff"], state.get("repo_patterns", []))
    return {"security_findings": findings}


async def _node_style(state: ReviewState) -> dict:
    findings = await style.run(state["diff"], state.get("repo_patterns", []))
    return {"style_findings": findings}


async def _node_architecture(state: ReviewState) -> dict:
    findings = await architecture.run(state["diff"], state.get("repo_patterns", []))
    return {"architecture_findings": findings}


async def _node_merge(state: ReviewState) -> dict:
    agent_results = {
        "static_analysis": state.get("static_analysis_findings", []),
        "security": state.get("security_findings", []),
        "style": state.get("style_findings", []),
        "architecture": state.get("architecture_findings", []),
    }
    merged = merge_and_dedupe(agent_results)
    summary = build_summary(merged, state["repo_full_name"], state["pr_number"])
    return {"merged_findings": merged, "summary": summary}


def build_review_graph():
    """Compiles and returns the LangGraph app for a single review run."""
    graph = StateGraph(ReviewState)

    graph.add_node("static_analysis", _node_static_analysis)
    graph.add_node("security", _node_security)
    graph.add_node("style", _node_style)
    graph.add_node("architecture", _node_architecture)
    graph.add_node("merge_findings", _node_merge)

    # Fan-out: entry point branches into all four agents, which run concurrently
    graph.set_entry_point("static_analysis")
    graph.add_edge("static_analysis", "merge_findings")
    # LangGraph runs nodes with no unmet dependencies concurrently once we also
    # register the other three as additional entry points feeding the same sink.
    graph.set_entry_point("security")
    graph.add_edge("security", "merge_findings")
    graph.set_entry_point("style")
    graph.add_edge("style", "merge_findings")
    graph.set_entry_point("architecture")
    graph.add_edge("architecture", "merge_findings")

    graph.add_edge("merge_findings", END)

    return graph.compile()


_compiled_graph = None


def get_review_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_review_graph()
    return _compiled_graph


async def run_review_graph(repo_full_name: str, pr_number: int, diff: str, repo_patterns: list[dict]) -> ReviewState:
    """Convenience entrypoint used by the Celery task."""
    app = get_review_graph()
    initial_state: ReviewState = {
        "repo_full_name": repo_full_name,
        "pr_number": pr_number,
        "diff": diff,
        "repo_patterns": repo_patterns,
    }
    final_state = await app.ainvoke(initial_state)
    return final_state
