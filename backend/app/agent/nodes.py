"""Single-purpose LangGraph nodes with injected services."""

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict

from pydantic import ValidationError

from app.agent.prompts import (
    EXPLAINER_PROMPT,
    GENERATOR_PROMPT,
    ROUTER_PROMPT,
    build_messages,
)
from app.models.agent import AgentState
from app.models.chat import Explanation, IntentDecision
from app.services.database import DatabaseService
from app.services.llm import LanguageModel, ModelUnavailableError
from app.services.request_policy import requests_destructive_operation
from app.services.sql_validation import SQLValidationError, SQLValidator


@dataclass(frozen=True)
class AgentDependencies:
    """Services constructed once at startup and explicitly injected into nodes."""

    database: DatabaseService
    validator: SQLValidator
    model: LanguageModel


async def router_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Classify the latest user request without generating or executing SQL.

    Args:
        state: Current messages and previous query.
        dependencies: Injected model and trusted schema provider.

    Returns:
        Intent, refusal flag, or clarification question. Calls the LLM when needed.
    """
    message = str(state["messages"][-1].content)
    if requests_destructive_operation(message):
        return {"intent": "out_of_scope", "destructive": True}
    raw = await dependencies.model.complete(
        build_messages(ROUTER_PROMPT, state, dependencies.database.schema), json_output=True
    )
    try:
        decision = IntentDecision.model_validate_json(raw)
    except ValidationError as error:
        raise ModelUnavailableError(
            "The model returned an invalid routing response. Try again."
        ) from error
    return decision.model_dump()


def _extract_debug_sql(message: str, previous_sql: str | None) -> str:
    """Extract a likely SQL statement from a debug request or its prior query."""
    match = re.search(r"\b(?:SELECT|WITH)\b[\s\S]*", message, re.IGNORECASE)
    return (match.group(0) if match else (previous_sql or "")).strip()


def debug_inspection_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Validate the user's original debug SQL before asking for a correction.

    Args:
        state: Routed debug request containing the latest user text and previous SQL.
        dependencies: Injected schema-aware SQL validator.

    Returns:
        Original SQL and its first validation error, if any. This node does not execute
        SQL or count a retry; the generator remains responsible for producing a repair.
    """
    latest_message = str(state["messages"][-1].content)
    candidate_sql = _extract_debug_sql(latest_message, state["previous_sql"])
    if not candidate_sql:
        return {
            "intent": "clarify",
            "clarification": "Please include the SQL query you want me to debug.",
        }
    try:
        validated_sql = dependencies.validator.validate(candidate_sql)
    except SQLValidationError as error:
        error_message = f"Original SQL error: {error}"
        return {
            "generated_sql": candidate_sql,
            "error_msg": error_message,
            "original_error": error_message,
        }
    return {"generated_sql": validated_sql, "error_msg": None}


async def sql_generator_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Generate or repair one candidate using intent, previous SQL, and error context.

    Args:
        state: Original conversation and latest failure, if any.
        dependencies: Injected model and schema provider.

    Returns:
        Candidate SQL and cleared transient results. Makes one LLM request.
    """
    generated_sql = await dependencies.model.complete(
        build_messages(GENERATOR_PROMPT, state, dependencies.database.schema)
    )
    return {
        "generated_sql": generated_sql,
        "is_valid": False,
        "error_msg": None,
        "query_results": None,
    }


def validation_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Validate candidate SQL without making model or database execution calls.

    Args:
        state: Generated SQL and number of previous failed attempts.
        dependencies: Injected SQLGlot/schema validator.

    Returns:
        Canonical validated SQL or one failure increment and explicit error context.
    """
    try:
        sql = dependencies.validator.validate(state["generated_sql"])
        return {"generated_sql": sql, "is_valid": True, "error_msg": None}
    except SQLValidationError as error:
        error_message = str(error)
        update: Dict[str, Any] = {
            "is_valid": False,
            "error_msg": error_message,
            "retry_count": state["retry_count"] + 1,
        }
        if state["original_error"] is None:
            update["original_error"] = error_message
        return update


async def executor_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Execute the validated query through the independent SQLite safety boundary.

    Args:
        state: Validated SQL and current failure count.
        dependencies: Injected read-only database service.

    Returns:
        Bounded query results or one failure increment. Opens a short-lived connection.
    """
    if not state["is_valid"]:
        raise RuntimeError("Executor requires validated SQL.")
    try:
        results = await asyncio.to_thread(dependencies.database.execute, state["generated_sql"])
        return {"query_results": results, "error_msg": None}
    except sqlite3.DatabaseError as error:
        error_message = str(error)
        update: Dict[str, Any] = {
            "is_valid": False,
            "error_msg": error_message,
            "query_results": None,
            "retry_count": state["retry_count"] + 1,
        }
        if state["original_error"] is None:
            update["original_error"] = error_message
        return update


def safe_explanation(text: str) -> bool:
    """Check explanation text for executable write statements or fenced code.

    Args:
        text: Untrusted prose generated by the model.

    Returns:
        True if no obvious executable write SQL is present; performs no I/O.
    """
    return not re.search(
        r"```|\b(?:CREATE\s+(?:UNIQUE\s+)?INDEX|DROP\s+TABLE|DELETE\s+FROM|"
        r"INSERT\s+INTO|UPDATE\s+\w+\s+SET|ALTER\s+TABLE|TRUNCATE\s+TABLE)\b",
        text,
        re.IGNORECASE,
    )


async def explainer_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Explain the successful query and any debugging or optimization changes.

    Args:
        state: Validated SQL, original conversation, and execution results.
        dependencies: Injected LLM and trusted schema.

    Returns:
        English explanation and task-specific advice. Makes one LLM request.
    """
    raw = await dependencies.model.complete(
        build_messages(EXPLAINER_PROMPT, state, dependencies.database.schema), json_output=True
    )
    try:
        explanation = Explanation.model_validate_json(raw)
        texts = [
            explanation.explanation,
            explanation.original_error or "",
            *explanation.optimization_tips,
        ]
        if not all(safe_explanation(text) for text in texts):
            raise ValueError("Unsafe explanation.")
        if (
            state["intent"] == "debug"
            and state["original_error"]
            and not explanation.original_error
        ):
            explanation = explanation.model_copy(update={"original_error": state["original_error"]})
        if state["intent"] == "optimize" and not explanation.optimization_tips:
            raise ValueError("Optimization advice is missing.")
    except (ValidationError, ValueError) as error:
        raise ModelUnavailableError(
            "The model returned an invalid explanation. Please try again."
        ) from error
    return {**explanation.model_dump(), "status": "success"}


def clarification_node(state: AgentState) -> Dict[str, Any]:
    """Return an actionable clarification without generating a query.

    Args:
        state: Router's clarification question and conversational context.

    Returns:
        Clarification status and safe question. No external side effects.
    """
    question = state["clarification"]
    if not question or not safe_explanation(question):
        question = "Which records, filters, or SQL query would you like me to work with?"
    return {"status": "clarification", "explanation": question}


def rejection_node(state: AgentState) -> Dict[str, Any]:
    """Politely refuse unsupported or destructive requests without calling services.

    Args:
        state: Router classification and destructive-request flag.

    Returns:
        A deterministic rejection response with no generated SQL.
    """
    message = (
        "I can help read and understand your data, but I cannot create queries that change "
        "or delete data or database structures."
        if state["destructive"]
        else "I can help with SQL and this ecommerce database. Try asking about users, orders, "
        "products, or order items."
    )
    return {"status": "rejected", "explanation": message}


def fallback_node(state: AgentState) -> Dict[str, Any]:
    """Finish after three failed attempts without exposing an invalid SQL candidate.

    Args:
        state: Last error and exhausted failure counter.

    Returns:
        A controlled error response, clearing unsafe candidate SQL and results.
    """
    unsupported_function = "not authorized to use function" in (state["error_msg"] or "")
    message = (
        "This query uses a SQL function that is not supported by the read-only database policy. "
        "Try a supported aggregate or a simpler list/filter request."
        if unsupported_function
        else "I couldn't produce a valid query after three attempts. Please clarify the columns, "
        "filters, or relationships you need."
    )
    return {
        "status": "error",
        "explanation": message,
        "generated_sql": "",
        "is_valid": False,
        "query_results": None,
        "error_msg": message,
    }
