"""Cyclical LangGraph workflow with explicit terminal paths."""

from functools import partial
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import (
    AgentDependencies,
    clarification_node,
    executor_node,
    explainer_node,
    fallback_node,
    rejection_node,
    router_node,
    sql_generator_node,
    validation_node,
)
from app.models.agent import AgentState


def route_intent(state: AgentState) -> Literal["reject", "clarify", "generate"]:
    """Choose the next node from the router's state without side effects.

    Args:
        state: Classified intent and destructive flag.

    Returns:
        Rejection, clarification, or SQL generation node name.
    """
    if state["destructive"] or state["intent"] == "out_of_scope":
        return "reject"
    if state["intent"] == "clarify":
        return "clarify"
    return "generate"


def route_validation(state: AgentState) -> Literal["execute", "generate", "fallback"]:
    """Select execution, repair, or terminal fallback after validation.

    Args:
        state: Validation result and failure count.

    Returns:
        Next node name without changing the state.
    """
    if state["is_valid"]:
        return "execute"
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
    graph.add_node("generate", partial(sql_generator_node, dependencies=dependencies))
    graph.add_node("validate", partial(validation_node, dependencies=dependencies))
    graph.add_node("execute", partial(executor_node, dependencies=dependencies))
    graph.add_node("explain", partial(explainer_node, dependencies=dependencies))
    graph.add_node("clarify", clarification_node)
    graph.add_node("reject", rejection_node)
    graph.add_node("fallback", fallback_node)
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_intent)
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", route_validation)
    graph.add_conditional_edges("execute", route_execution)
    for terminal_node in ["explain", "clarify", "reject", "fallback"]:
        graph.add_edge(terminal_node, END)
    return graph.compile()
