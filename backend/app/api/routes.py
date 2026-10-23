"""Chat transport and safe projections of internal graph state."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from app.api.dependencies import get_database, get_graph
from app.models.agent import AgentState
from app.models.chat import ChatRequest, ChatResponse
from app.models.database import DatabaseSchema
from app.services.database import DatabaseService
from app.services.llm import ModelUnavailableError

router = APIRouter()


def initial_state(payload: ChatRequest) -> AgentState:
    """Convert bounded client history into a fresh per-turn graph state.

    Args:
        payload: Validated request with only user/assistant message roles.

    Returns:
        New state with a zeroed retry counter; input data remains untrusted.
    """
    messages = [
        (HumanMessage if message.role == "user" else AIMessage)(
            content=message.content + (f"\nPrevious query:\n{message.sql}" if message.sql else "")
        )
        for message in payload.history
    ]
    previous_sql = payload.previous_sql or next(
        (
            message.sql
            for message in reversed(payload.history)
            if message.role == "assistant" and message.sql
        ),
        None,
    )
    return AgentState(
        messages=[*messages, HumanMessage(content=payload.message)],
        intent="query",
        previous_sql=previous_sql,
        generated_sql="",
        is_valid=False,
        error_msg=None,
        retry_count=0,
        explanation="",
        query_results=None,
        status="error",
        destructive=False,
        clarification="",
        original_error=None,
        optimization_tips=[],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, graph: Annotated[CompiledStateGraph, Depends(get_graph)]
) -> ChatResponse:
    """Run one graph turn and expose only a safe public response.

    Args:
        payload: Message and conversational context.
        graph: Injected compiled LangGraph workflow.

    Returns:
        Final response containing SQL only after successful validation and execution.

    Side Effects:
        Invokes the model and performs bounded read-only queries through graph nodes.
    """
    try:
        state = await graph.ainvoke(initial_state(payload), config={"recursion_limit": 24})
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GraphRecursionError as error:
        raise HTTPException(
            status_code=500, detail="Query processing exceeded its step limit."
        ) from error
    successful = state["status"] == "success" and state["is_valid"]
    return ChatResponse(
        status=state["status"],
        intent=state["intent"],
        generated_sql=state["generated_sql"] if successful else None,
        previous_sql=state["generated_sql"] if successful else None,
        is_valid=successful,
        retry_count=state["retry_count"],
        error_msg=state["error_msg"],
        explanation=state["explanation"],
        original_error=state["original_error"],
        optimization_tips=state["optimization_tips"],
        query_results=state["query_results"] if successful else None,
    )


@router.get("/schema", response_model=DatabaseSchema)
def schema(database: Annotated[DatabaseService, Depends(get_database)]) -> DatabaseSchema:
    """Expose the sample schema for the UI without accepting SQL.

    Args:
        database: Injected service whose metadata was read at startup.

    Returns:
        Cached application schema; no external side effects.
    """
    return database.schema


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    """Report service readiness without exposing credentials.

    Args:
        request: Request used to read startup configuration status.

    Returns:
        Database availability and whether the model has been configured.
    """
    return {"status": "ok", "model_configured": request.app.state.model_configured}
