"""HTTP and LLM output schemas."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.database import QueryResults

Intent = Literal["query", "optimize", "debug", "out_of_scope", "clarify"]
ResponseStatus = Literal["success", "rejected", "clarification", "error"]


class ChatMessage(BaseModel):
    """A client-visible message; clients cannot supply system instructions."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)
    sql: Optional[str] = Field(default=None, max_length=12000)


class ChatRequest(BaseModel):
    """A new message and its bounded conversational context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=30)
    previous_sql: Optional[str] = Field(default=None, max_length=12000)


class ChatResponse(BaseModel):
    """Safe, serializable public projection of the final graph state."""

    status: ResponseStatus
    intent: Intent
    generated_sql: Optional[str] = None
    previous_sql: Optional[str] = None
    is_valid: bool = False
    error_msg: Optional[str] = None
    retry_count: int = 0
    explanation: str
    original_error: Optional[str] = None
    optimization_tips: List[str] = Field(default_factory=list)
    query_results: Optional[QueryResults] = None


class IntentDecision(BaseModel):
    """Structured routing result, including a separate destructive-request flag."""

    intent: Intent
    destructive: bool = False
    clarification: str = ""


class Explanation(BaseModel):
    """Explanation of the final SQL and optional task-specific advice."""

    explanation: str = Field(min_length=1, max_length=4000)
    original_error: Optional[str] = Field(default=None, max_length=2000)
    optimization_tips: List[str] = Field(default_factory=list, max_length=6)
