"""Deterministic graph integration tests with real SQLite and scripted model responses."""

import json
from typing import List

import pytest
from langchain_core.messages import BaseMessage

from app.agent.graph import build_graph
from app.agent.nodes import AgentDependencies
from app.api.routes import initial_state
from app.models.chat import ChatMessage, ChatRequest
from app.services.database import DatabaseService
from app.services.sql_validation import SQLValidator


class ScriptedModel:
    """Supply controlled model outputs while recording the complete prompt context."""

    def __init__(self, responses: List[str]) -> None:
        """Store ordered responses and initialize captured message calls."""
        self.responses = iter(responses)
        self.calls: List[List[BaseMessage]] = []

    async def complete(self, messages: List[BaseMessage], json_output: bool = False) -> str:
        """Record a model request and return the next response without network access."""
        self.calls.append(messages)
        return next(self.responses)


def decision(intent: str = "query", **fields: object) -> str:
    """Create a structured router response for a test scenario."""
    return json.dumps({"intent": intent, **fields})


def explanation(**fields: object) -> str:
    """Create a structured explanation response for a test scenario."""
    return json.dumps({"explanation": "Lists users in the requested state.", **fields})


@pytest.mark.parametrize(
    "bad_sql",
    [
        "SELECT name FROM Missing",
        "SELECT * FROM Users WHERE (",
        "SELECT imaginary_function(name) FROM Users",
        "DROP TABLE Users",
    ],
)
async def test_graph_repairs_validation_and_execution_errors(
    database: DatabaseService, bad_sql: str
) -> None:
    """Both validator errors and actual SQLite failures route back with error context."""
    model = ScriptedModel(
        [
            decision(),
            bad_sql,
            "SELECT name FROM Users WHERE state='California'",
            explanation(),
        ]
    )
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Show California users")))
    assert result["status"] == "success"
    assert result["retry_count"] == 1
    assert len(result["query_results"].rows) == 3
    repair_context = json.loads(str(model.calls[2][-1].content).split("\n", 1)[1])
    assert repair_context["failed_sql"]
    if "imaginary_function" in bad_sql:
        assert "imaginary_function" in repair_context["failed_sql"].lower()
    else:
        assert repair_context["failed_sql"] == bad_sql
    assert '"last_error": null' not in str(model.calls[2][-1].content)


async def test_graph_stops_after_three_failed_attempts(database: DatabaseService) -> None:
    """Repeated failures terminate without disclosing invalid SQL in the final state."""
    model = ScriptedModel([decision(), *["SELECT fake FROM Users"] * 3])
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Show users")))
    assert result["retry_count"] == 3
    assert result["status"] == "error"
    assert result["generated_sql"] == ""
    assert result["query_results"] is None
    assert len(model.calls) == 4


async def test_followup_keeps_previous_sql_and_messages(database: DatabaseService) -> None:
    """A contextual follow-up receives the previous SQL and returns the correct subset."""
    model = ScriptedModel(
        [
            decision(),
            "SELECT name FROM Users WHERE state='California'",
            explanation(),
        ]
    )
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    request = ChatRequest(
        message="Only California",
        history=[
            ChatMessage(role="user", content="Show all customers"),
            ChatMessage(
                role="assistant", content="Here are the customers.", sql="SELECT name FROM Users"
            ),
        ],
    )
    result = await graph.ainvoke(initial_state(request))
    assert result["query_results"].rows == [["Maya Chen"], ["Ava Patel"], ["Owen Davis"]]
    assert "SELECT name FROM Users" in str(model.calls[1][-1].content)
    assert len(result["messages"]) == 3


@pytest.mark.parametrize(
    "intent,status", [("out_of_scope", "rejected"), ("clarify", "clarification")]
)
async def test_non_query_routes_never_generate_sql(
    database: DatabaseService, intent: str, status: str
) -> None:
    """Rejection and clarification terminate after routing without candidate generation."""
    model = ScriptedModel([decision(intent, clarification="Which order status do you mean?")])
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Tell me more")))
    assert result["status"] == status
    assert result["generated_sql"] == ""
    assert len(model.calls) == 1


async def test_destructive_request_never_calls_model(database: DatabaseService) -> None:
    """Explicit destructive requests are refused before model generation."""
    model = ScriptedModel([])
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Delete all users")))
    assert result["status"] == "rejected"
    assert not model.calls


@pytest.mark.parametrize(
    "intent,details",
    [
        ("debug", {"original_error": "The column fullname does not exist; use name."}),
        (
            "optimize",
            {"optimization_tips": ["An index on Users.state may help repeated state filters."]},
        ),
    ],
)
async def test_debugging_and_optimization_return_task_details(
    database: DatabaseService, intent: str, details: dict[str, object]
) -> None:
    """Specialized routes preserve their intent and return explanation details."""
    model = ScriptedModel([decision(intent), "SELECT name FROM Users", explanation(**details)])
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Help with this SQL")))
    assert result["status"] == "success"
    for key, value in details.items():
        assert result[key] == value


async def test_valid_debug_query_does_not_require_an_original_error(
    database: DatabaseService,
) -> None:
    """A valid SQL validation request can explain success without inventing an error."""
    model = ScriptedModel(
        [
            decision("debug"),
            "SELECT name FROM Users",
            explanation(),
        ]
    )
    graph = build_graph(AgentDependencies(database, SQLValidator(database.schema), model))
    result = await graph.ainvoke(initial_state(ChatRequest(message="Validate this SQL query")))
    assert result["status"] == "success"
    assert result["original_error"] is None
