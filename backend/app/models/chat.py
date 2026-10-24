"""HTTP and LLM output schemas."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.database import QueryResults

Intent = Literal["query", "optimize", "debug", "out_of_scope", "clarify"]
SQLDialect = Literal["sqlite", "postgresql", "mysql"]
ResponseStatus = Literal["success", "rejected", "clarification", "error"]


class ChatMessage(BaseModel):
    """A client-visible message; clients cannot supply system instructions."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)
    sql: Optional[str] = Field(default=None, max_length=12000)


class PersistedChatMessage(BaseModel):
    """A complete message retained by the server-side conversation store."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(min_length=1, max_length=100)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)
    sql: Optional[str] = Field(default=None, max_length=12000)
    response: Optional["ChatResponse"] = None


class ChatSession(BaseModel):
    """A bounded conversation snapshot stored for one client identifier."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    created_at: str = Field(alias="createdAt", min_length=1, max_length=80)
    updated_at: str = Field(alias="updatedAt", min_length=1, max_length=80)
    messages: List[PersistedChatMessage] = Field(default_factory=list, max_length=60)
    previous_sql: Optional[str] = Field(default=None, alias="previousSql", max_length=12000)
    selected_response: Optional["ChatResponse"] = Field(default=None, alias="selectedResponse")


class SessionListResponse(BaseModel):
    """Server response containing the client's available conversations."""

    sessions: List[ChatSession] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """A new message and its bounded conversational context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    history: List[ChatMessage] = Field(default_factory=list, max_length=30)
    previous_sql: Optional[str] = Field(default=None, max_length=12000)
    dialect: SQLDialect = "sqlite"


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
    dialect: SQLDialect = "sqlite"


class SQLRunRequest(BaseModel):
    """A SQL statement submitted from the editor for guarded execution."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sql: str = Field(min_length=1, max_length=12000)
    dialect: SQLDialect = "sqlite"


class SQLRunResponse(BaseModel):
    """Validated SQL and bounded results returned by the editor execution endpoint."""

    sql: str
    query_results: QueryResults
    dialect: SQLDialect = "sqlite"


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


PersistedChatMessage.model_rebuild()
ChatSession.model_rebuild()
