"""Cyclical LangGraph workflow with explicit terminal paths."""

from functools import partial
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import (
    AgentDependencies,
    clarification_node,
    debug_inspection_node,
    executor_node,
    explainer_node,
    fallback_node,
    optimization_node,
    rejection_node,
    router_node,
    schema_retrieval_node,
    scope_validation_node,
    sql_generator_node,
    validation_node,
)
from app.models.agent import AgentState


def route_scope(state: AgentState) -> Literal["reject", "clarify", "schema_retrieval"]:
    """Choose the next node after explicit scope validation.

    Args:
        state: Classified intent and destructive flag.

    Returns:
        Rejection, clarification, or trusted schema retrieval node name.
    """
    if state["destructive"] or state["intent"] == "out_of_scope":
        return "reject"
    if state["intent"] == "clarify":
        return "clarify"
    return "schema_retrieval"


def route_schema(state: AgentState) -> Literal["inspect_debug", "generate"]:
    """Route retrieved schema context into debugging or SQL generation."""
    if state["intent"] == "debug":
        return "inspect_debug"
    return "generate"


def route_debug_inspection(
    state: AgentState,
) -> Literal["clarify", "generate", "optimization"]:
    """Route an inspected debug request to repair or the safe execution pipeline.

    A context correction is already validated by ``debug_inspection_node`` and can
    therefore continue through optimization, execution, and explanation without an
    unnecessary model generation call.
    """
    if state["intent"] == "clarify":
        return "clarify"
    if state["context_corrected"]:
        return "optimization"
    return "generate"


def route_validation(state: AgentState) -> Literal["optimization", "generate", "fallback"]:
    """Select execution, repair, or terminal fallback after validation.

    Args:
        state: Validation result and failure count.

    Returns:
        Optimization, repair, or terminal fallback node name.
    """
    if state["is_valid"]:
        return "optimization"
    return "fallback" if state["retry_count"] >= 3 else "generate"


def route_execution(state: AgentState) -> Literal["explain", "generate", "fallback"]:
    """Select explanation or bounded repair after SQLite execution.

    Args:
        state: Execution error and failure count.

    Returns:
        Next node name without changing the state.
    """
    if state["error_msg"] is None:
        return "explain"
    return "fallback" if state["retry_count"] >= 3 else "generate"


def build_graph(dependencies: AgentDependencies) -> CompiledStateGraph:
    """Bind injected services and compile the SQL workflow.

    Args:
        dependencies: Database, validator, and model instances owned by the application.

    Returns:
        Compiled graph. Construction makes no LLM calls and executes no SQL.
    """
    graph = StateGraph(AgentState)
    graph.add_node("router", partial(router_node, dependencies=dependencies))
    graph.add_node("scope_validation", partial(scope_validation_node, dependencies=dependencies))
    graph.add_node("schema_retrieval", partial(schema_retrieval_node, dependencies=dependencies))
    graph.add_node("optimization", optimization_node)
    graph.add_node("generate", partial(sql_generator_node, dependencies=dependencies))
    graph.add_node("inspect_debug", partial(debug_inspection_node, dependencies=dependencies))
    graph.add_node("validate", partial(validation_node, dependencies=dependencies))
    graph.add_node("execute", partial(executor_node, dependencies=dependencies))
    graph.add_node("explain", partial(explainer_node, dependencies=dependencies))
    graph.add_node("clarify", clarification_node)
    graph.add_node("reject", rejection_node)
    graph.add_node("fallback", fallback_node)
    graph.add_edge(START, "router")
    graph.add_edge("router", "scope_validation")
    graph.add_conditional_edges("scope_validation", route_scope)
    graph.add_conditional_edges("schema_retrieval", route_schema)
    graph.add_conditional_edges("inspect_debug", route_debug_inspection)
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", route_validation)
    graph.add_edge("optimization", "execute")
    graph.add_conditional_edges("execute", route_execution)
    for terminal_node in ["explain", "clarify", "reject", "fallback"]:
        graph.add_edge(terminal_node, END)
    return graph.compile()
