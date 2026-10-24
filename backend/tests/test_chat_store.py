"""Server-side conversation persistence tests."""

from pathlib import Path

from app.models.chat import ChatResponse, ChatSession, PersistedChatMessage
from app.services.chat_store import DatabaseChatStore


def session(session_id: str, title: str = "Question") -> ChatSession:
    """Build a small valid session fixture."""
    response = ChatResponse(
        status="success",
        intent="query",
        generated_sql="SELECT name FROM Users",
        previous_sql="SELECT name FROM Users",
        is_valid=True,
        explanation="Lists users.",
    )
    return ChatSession(
        id=session_id,
        title=title,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at=f"2026-01-01T00:00:0{session_id[-1]}+00:00",
        messages=[
            PersistedChatMessage(
                id=f"message-{session_id}",
                role="assistant",
                content="Lists users.",
                sql=response.generated_sql,
                response=response,
            )
        ],
        previous_sql=response.generated_sql,
        selected_response=response,
    )


def test_sqlite_chat_store_is_client_scoped_and_persistent(tmp_path: Path) -> None:
    """A reopened store retains sessions but never exposes another client."""
    database_url = f"sqlite:///{tmp_path / 'chat.db'}"
    store = DatabaseChatStore(database_url)
    store.initialize()
    store.upsert_session("client-a", session("one"))
    store.upsert_session("client-b", session("two"))
    store.close()

    reopened = DatabaseChatStore(database_url)
    reopened.initialize()
    assert [item.id for item in reopened.list_sessions("client-a")] == ["one"]
    assert reopened.get_session("client-a", "two") is None


def test_sqlite_chat_store_prunes_old_sessions(tmp_path: Path) -> None:
    """The server-side cap prevents an unbounded conversation collection."""
    store = DatabaseChatStore(f"sqlite:///{tmp_path / 'chat.db'}", max_sessions=2)
    store.initialize()
    store.upsert_session("client-a", session("one"))
    store.upsert_session("client-a", session("two"))
    store.upsert_session("client-a", session("three"))

    assert len(store.list_sessions("client-a")) == 2
