"""Typed state shared by LangGraph nodes."""

from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.models.chat import Intent, ResponseStatus
from app.models.database import QueryResults


class AgentState(TypedDict):
    """Per-turn state; failure count is preserved only across repair cycles."""

    messages: Annotated[List[BaseMessage], add_messages]
    intent: Intent
    previous_sql: Optional[str]
    generated_sql: str
    is_valid: bool
    error_msg: Optional[str]
    retry_count: int
    explanation: str
    query_results: Optional[QueryResults]
    status: ResponseStatus
    destructive: bool
    clarification: str
    original_error: Optional[str]
    optimization_tips: List[str]
