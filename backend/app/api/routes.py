"""Chat transport and safe projections of internal graph state."""

import asyncio
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from app.api.dependencies import get_chat_store, get_database, get_graph, get_sql_validator
from app.models.agent import AgentState
from app.models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSession,
    PersistedChatMessage,
    SessionListResponse,
    SQLRunRequest,
    SQLRunResponse,
)
from app.models.database import DatabaseSchema
from app.services.chat_store import ChatStore, ChatStoreError
from app.services.database import DatabaseService
from app.services.llm import ModelUnavailableError
from app.services.sql_validation import SQLValidationError, SQLValidator

router = APIRouter()
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_optional_client_id(
    client_id: Annotated[Optional[str], Header(alias="X-Client-ID")] = None,
) -> Optional[str]:
    """Validate an optional opaque browser identifier used for chat ownership.

    Args:
        client_id: Value from the ``X-Client-ID`` request header.

    Returns:
        A bounded identifier or ``None`` for legacy stateless chat callers.

    Raises:
        HTTPException: If the supplied identifier contains unsafe/unbounded input.
    """
    if client_id is not None and not CLIENT_ID_PATTERN.fullmatch(client_id):
        raise HTTPException(status_code=400, detail="X-Client-ID is invalid.")
    return client_id


def require_client_id(client_id: Annotated[Optional[str], Depends(get_optional_client_id)]) -> str:
    """Require a client identifier for server-side session endpoints."""
    if client_id is None:
        raise HTTPException(status_code=400, detail="X-Client-ID is required.")
    return client_id


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
        schema_context="",
        optimization_context="",
    )


def _history_from_session(session: ChatSession) -> List[ChatMessage]:
    """Convert persisted messages to the graph's intentionally smaller input model."""
    return [
        ChatMessage(role=message.role, content=message.content, sql=message.sql)
        for message in session.messages
    ]


def _session_after_turn(
    existing_session: Optional[ChatSession],
    payload: ChatRequest,
    response: ChatResponse,
) -> ChatSession:
    """Append a completed turn to a bounded session snapshot.

    Args:
        existing_session: Server copy before this request, if synchronized already.
        payload: User request containing the current message and session identifier.
        response: Safe public graph response to retain with the assistant message.

    Returns:
        Session snapshot ready for the injected ``ChatStore``.
    """
    now = datetime.now(timezone.utc).isoformat()
    if existing_session is not None:
        messages = list(existing_session.messages)
        created_at = existing_session.created_at
        title = existing_session.title
        previous_sql = existing_session.previous_sql
    else:
        messages = [
            PersistedChatMessage(
                id=str(uuid4()), role=message.role, content=message.content, sql=message.sql
            )
            for message in payload.history
        ]
        created_at = now
        title = payload.message[:42].strip() or "New conversation"
        previous_sql = payload.previous_sql
    if not messages:
        title = payload.message[:42].strip() or "New conversation"
    messages.extend(
        [
            PersistedChatMessage(id=str(uuid4()), role="user", content=payload.message),
            PersistedChatMessage(
                id=str(uuid4()),
                role="assistant",
                content=response.explanation,
                sql=response.generated_sql,
                response=response,
            ),
        ]
    )
    return ChatSession(
        id=payload.session_id or str(uuid4()),
        title=title,
        created_at=created_at,
        updated_at=now,
        messages=messages[-60:],
        previous_sql=response.generated_sql or previous_sql,
        selected_response=response,
    )


async def _process_chat(
    payload: ChatRequest,
    graph: CompiledStateGraph,
    chat_store: ChatStore,
    client_id: Optional[str],
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
    existing_session = None
    effective_payload = payload
    if payload.session_id:
        if client_id is None:
            raise HTTPException(status_code=400, detail="X-Client-ID is required for a session.")
        try:
            existing_session = chat_store.get_session(client_id, payload.session_id)
        except ChatStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if existing_session is not None:
            effective_payload = payload.model_copy(
                update={
                    "history": _history_from_session(existing_session),
                    "previous_sql": existing_session.previous_sql,
                }
            )
    try:
        state = await graph.ainvoke(
            initial_state(effective_payload), config={"recursion_limit": 24}
        )
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GraphRecursionError as error:
        raise HTTPException(
            status_code=500, detail="Query processing exceeded its step limit."
        ) from error
    successful = state["status"] == "success" and state["is_valid"]
    response = ChatResponse(
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
    if payload.session_id and client_id is not None:
        try:
            chat_store.upsert_session(
                client_id, _session_after_turn(existing_session, payload, response)
            )
        except ChatStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    return response


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_graph)],
    chat_store: Annotated[ChatStore, Depends(get_chat_store)],
    client_id: Annotated[Optional[str], Depends(get_optional_client_id)],
) -> ChatResponse:
    """Run one complete graph turn for clients that prefer a regular JSON response."""
    return await _process_chat(payload, graph, chat_store, client_id)


def _sse_event(event_name: str, payload: object) -> str:
    """Encode one JSON Server-Sent Event frame."""
    return f"event: {event_name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def _stream_explanation(explanation: str, chunk_size: int = 72) -> AsyncIterator[str]:
    """Yield safe explanation text in small frames after the graph succeeds."""
    for offset in range(0, len(explanation), chunk_size):
        yield _sse_event("chunk", {"text": explanation[offset : offset + chunk_size]})
        await asyncio.sleep(0)


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_graph)],
    chat_store: Annotated[ChatStore, Depends(get_chat_store)],
    client_id: Annotated[Optional[str], Depends(get_optional_client_id)],
) -> StreamingResponse:
    """Stream progress, explanation chunks, and the final guarded response as SSE.

    SQL and result rows are emitted only in the final event, after the same AST,
    schema, and read-only execution checks used by the JSON endpoint have passed.
    """

    async def events() -> AsyncIterator[str]:
        """Run one turn and translate its safe milestones into SSE frames."""
        yield _sse_event("status", {"state": "processing"})
        try:
            response = await _process_chat(payload, graph, chat_store, client_id)
            async for chunk in _stream_explanation(response.explanation):
                yield chunk
            yield _sse_event("complete", {"response": response.model_dump(mode="json")})
        except HTTPException as error:
            yield _sse_event("error", {"detail": str(error.detail), "status": error.status_code})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    client_id: Annotated[str, Depends(require_client_id)],
    chat_store: Annotated[ChatStore, Depends(get_chat_store)],
) -> SessionListResponse:
    """List the current browser's persisted conversation sessions."""
    try:
        return SessionListResponse(sessions=chat_store.list_sessions(client_id))
    except ChatStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.put("/sessions/{session_id}", response_model=ChatSession)
def save_session(
    session_id: str,
    session: ChatSession,
    client_id: Annotated[str, Depends(require_client_id)],
    chat_store: Annotated[ChatStore, Depends(get_chat_store)],
) -> ChatSession:
    """Upsert a bounded browser session owned by the supplied client identifier."""
    if session_id != session.id:
        raise HTTPException(status_code=400, detail="Session id does not match the URL.")
    try:
        return chat_store.upsert_session(client_id, session)
    except ChatStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_session(
    session_id: str,
    client_id: Annotated[str, Depends(require_client_id)],
    chat_store: Annotated[ChatStore, Depends(get_chat_store)],
) -> Response:
    """Delete one browser-owned conversation from the server store."""
    try:
        chat_store.delete_session(client_id, session_id)
    except ChatStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run-sql", response_model=SQLRunResponse)
def run_sql(
    payload: SQLRunRequest,
    database: Annotated[DatabaseService, Depends(get_database)],
    sql_validator: Annotated[SQLValidator, Depends(get_sql_validator)],
) -> SQLRunResponse:
    """Validate and execute SQL submitted from the editor without invoking the model.

    Args:
        payload: Untrusted SQL text entered by the user.
        database: Injected read-only SQLite service with authorizer and limits.
        sql_validator: Shared SQLGlot and schema validator built at startup.

    Returns:
        Canonical validated SQL and bounded query results.

    Raises:
        HTTPException: If AST/schema validation or read-only execution fails.

    Side Effects:
        Opens a read-only SQLite connection; never modifies database contents.
    """
    try:
        validated_sql = sql_validator.validate(payload.sql)
        query_results = database.execute(validated_sql)
    except SQLValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except sqlite3.DatabaseError as error:
        raise HTTPException(status_code=400, detail=f"SQL execution failed: {error}") from error
    return SQLRunResponse(sql=validated_sql, query_results=query_results)


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
