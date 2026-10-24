"""Single-purpose LangGraph nodes with injected services."""

import asyncio
import json
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


def _model_json_object(raw: str) -> Dict[str, Any]:
    """Extract one JSON object from a model response without executing content.

    Args:
        raw: Model response that may contain a JSON fence or short surrounding prose.

    Returns:
        Parsed JSON object for subsequent Pydantic validation.

    Raises:
        ValueError: If no single JSON object can be parsed.
    """
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s*```$", "", normalized)
    if not normalized.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", normalized)
        if match is None:
            raise ValueError("Model response did not contain a JSON object.")
        normalized = match.group(0)
    value = json.loads(normalized)
    if not isinstance(value, dict):
        raise ValueError("Model response JSON must be an object.")
    return value


def _explicit_intent(message: str, previous_sql: str | None) -> str | None:
    """Recognize unambiguous SQL task wording before model classification.

    Args:
        message: Latest user request, treated as untrusted text.
        previous_sql: Server-provided prior query, if this is a follow-up turn.

    Returns:
        ``debug`` or ``optimize`` for explicit SQL tasks, otherwise ``None`` so
        the injected router model can handle normal questions and clarification.
    """
    has_sql = bool(re.search(r"\b(?:SELECT|WITH)\b", message, re.IGNORECASE))
    has_previous_sql = bool(previous_sql and previous_sql.strip())
    if not (has_sql or has_previous_sql):
        return None
    if re.search(
        r"\b(?:optimi[sz]e|optimization|performance|faster|readability|index|"
        r"unnecessary\s+joins?)\b",
        message,
        re.IGNORECASE,
    ):
        return "optimize"
    if re.search(
        r"\b(?:debug|validate|correct|fix|error|invalid|syntax|check)\b|"
        r"\b(?:is|does)\s+(?:this|the)\s+(?:sql|query)\b",
        message,
        re.IGNORECASE,
    ):
        return "debug"
    return None


def _obviously_out_of_scope(message: str, previous_sql: str | None) -> bool:
    """Recognize common non-SQL requests without misclassifying database questions.

    Args:
        message: Latest user request.
        previous_sql: Existing SQL context, if any.

    Returns:
        True only for strong out-of-scope signals with no SQL context.
    """
    if re.search(r"\b(?:SELECT|WITH)\b", message, re.IGNORECASE) or previous_sql:
        return False
    return bool(
        re.search(
            r"\b(?:fifa|world\s+cup|politic(?:s)?|president|election|football|nba|nfl|"
            r"weather|creative\s+writing|poem|poetry|song\s+lyrics|write\s+a\s+story|"
            r"tell\s+a\s+joke|python\s+programming|javascript\s+code)\b",
            message,
            re.IGNORECASE,
        )
    )


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
        decision = IntentDecision.model_validate(_model_json_object(raw))
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        raise ModelUnavailableError(
            "The model returned an invalid routing response. Try again."
        ) from error
    if _obviously_out_of_scope(message, state["previous_sql"]):
        decision.intent = "out_of_scope"
        decision.clarification = ""
    explicit_intent = _explicit_intent(message, state["previous_sql"])
    if explicit_intent is not None:
        decision.intent = explicit_intent
    return decision.model_dump()


def scope_validation_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Apply deterministic scope and destructive-request checks after intent detection.

    Args:
        state: Router output and the latest bounded user message.
        dependencies: Injected services; the database is not queried in this node.

    Returns:
        Scope corrections for out-of-scope or destructive requests, otherwise an empty update.
    """
    del dependencies
    message = str(state["messages"][-1].content)
    if requests_destructive_operation(message):
        return {"intent": "out_of_scope", "destructive": True}
    if _obviously_out_of_scope(message, state["previous_sql"]):
        return {"intent": "out_of_scope", "destructive": False, "clarification": ""}
    return {}


def schema_retrieval_node(state: AgentState, dependencies: AgentDependencies) -> Dict[str, Any]:
    """Retrieve the trusted schema context for downstream generation and validation.

    Args:
        state: Current turn state; not mutated directly.
        dependencies: Injected database service containing the trusted DDL.

    Returns:
        Schema DDL copied into graph state for the generator and explainer prompts.
    """
    del state
    return {"schema_context": dependencies.database.schema.ddl}


def optimization_node(state: AgentState) -> Dict[str, Any]:
    """Finalize the safe optimization phase after SQL validation.

    Args:
        state: State containing the validated candidate and classified intent.

    Returns:
        Bounded guidance consumed by the explainer; it never emits DDL or executes SQL.
    """
    if state["intent"] != "optimize":
        return {}
    return {
        "optimization_context": (
            "The candidate passed read-only validation. Explain readability and safe query "
            "structure improvements, remove only provably unnecessary joins, and reserve "
            "index recommendations for explanation prose. Never generate index-creation or "
            "other DDL."
        )
    }


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
        validated_sql = dependencies.validator.validate(candidate_sql, dialect=state["dialect"])
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
        sql = dependencies.validator.validate(
            state["generated_sql"], dialect=state["dialect"]
        )
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


def _default_optimization_tips(sql: str) -> list[str]:
    """Build conservative optimization prose when a model omits required tips."""
    tips = [
        (
            "Use an index on columns used repeatedly in WHERE or JOIN predicates, and confirm "
            "it helps with EXPLAIN QUERY PLAN before adding it."
        ),
    ]
    if re.search(r"\bJOIN\b", sql, re.IGNORECASE):
        tips.append(
            "The join should remain only when its columns or filtering are needed; otherwise "
            "remove it to avoid unnecessary row work."
        )
    if re.search(r"SELECT\s+\*", sql, re.IGNORECASE):
        tips.append("Select only the columns the client needs instead of using SELECT *.")
    else:
        tips.append(
            "The query already projects explicit columns, which keeps result transfer focused."
        )
    return tips[:6]


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
        explanation = Explanation.model_validate(_model_json_object(raw))
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
            explanation = explanation.model_copy(
                update={"optimization_tips": _default_optimization_tips(state["generated_sql"])}
            )
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
