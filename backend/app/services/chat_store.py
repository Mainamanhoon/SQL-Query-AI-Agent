"""Durable server-side conversation storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Protocol

from app.models.chat import ChatSession

try:
    from psycopg import Error as PostgresError
except ImportError:  # pragma: no cover - production dependencies include psycopg.
    class PostgresError(Exception):
        """Fallback error type when the optional local PostgreSQL driver is absent."""


class ChatStoreError(RuntimeError):
    """Raised when a conversation cannot be read or written."""


class ChatStore(Protocol):
    """Small persistence interface consumed by the HTTP layer."""

    def initialize(self) -> None:
        """Create the store schema if it does not exist."""

    def list_sessions(self, client_id: str) -> List[ChatSession]:
        """Return sessions belonging to one client identifier."""

    def get_session(self, client_id: str, session_id: str) -> Optional[ChatSession]:
        """Return one client-owned session, if it exists."""

    def upsert_session(self, client_id: str, session: ChatSession) -> ChatSession:
        """Insert or replace one client-owned session."""

    def delete_session(self, client_id: str, session_id: str) -> None:
        """Delete one client-owned session."""

    def close(self) -> None:
        """Release store resources."""


class DatabaseChatStore:
    """Persist conversations in SQLite locally or PostgreSQL in production.

    The chat store is deliberately separate from ``ecommerce.db``. The latter is
    opened read-only by the query engine and must never be used for application
    writes. PostgreSQL is selected by a ``postgresql://``/``postgres://`` URL,
    which is the required option for Vercel's ephemeral filesystem.
    """

    _schema_sql = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            client_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            session_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (client_id, session_id)
        )
    """
    _max_session_bytes = 2_000_000

    def __init__(self, database_url: str, max_sessions: int = 20) -> None:
        """Configure a store without opening a connection.

        Args:
            database_url: ``sqlite:///...`` for local use or a PostgreSQL URL.
            max_sessions: Maximum conversations retained for each client.
        """
        self.database_url = database_url.strip()
        self.max_sessions = max_sessions
        if not self.database_url:
            raise ChatStoreError("CHAT_DATABASE_URL is empty.")

    @property
    def is_postgres(self) -> bool:
        """Return whether this store uses the PostgreSQL adapter."""
        return self.database_url.startswith(("postgres://", "postgresql://"))

    def initialize(self) -> None:
        """Create the isolated chat table and its lookup index."""
        if self.is_postgres:
            with self._postgres_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._schema_sql)
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS chat_sessions_client_updated_idx
                        ON chat_sessions (client_id, updated_at DESC)
                        """
                    )
            return
        with self._sqlite_connection() as connection:
            connection.execute(self._schema_sql)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS chat_sessions_client_updated_idx
                ON chat_sessions (client_id, updated_at DESC)
                """
            )

    def list_sessions(self, client_id: str) -> List[ChatSession]:
        """Read all sessions for a client, newest first.

        Args:
            client_id: Browser-generated opaque identifier; no account data is inferred.

        Returns:
            Validated session snapshots owned by ``client_id``.

        Raises:
            ChatStoreError: If stored JSON is malformed or the database fails.
        """
        try:
            if self.is_postgres:
                with self._postgres_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT session_json FROM chat_sessions
                            WHERE client_id = %s ORDER BY updated_at DESC
                            """,
                            (client_id,),
                        )
                        rows = cursor.fetchall()
            else:
                with self._sqlite_connection() as connection:
                    rows = connection.execute(
                        """
                        SELECT session_json FROM chat_sessions
                        WHERE client_id = ? ORDER BY updated_at DESC
                        """,
                        (client_id,),
                    ).fetchall()
            return [self._decode(row[0]) for row in rows]
        except (sqlite3.Error, PostgresError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ChatStoreError(f"Could not load conversations: {error}") from error

    def get_session(self, client_id: str, session_id: str) -> Optional[ChatSession]:
        """Read a single client-owned session.

        Args:
            client_id: Opaque browser identifier used as the ownership boundary.
            session_id: Frontend conversation identifier.

        Returns:
            The session or ``None`` when it has not been synchronized yet.
        """
        try:
            if self.is_postgres:
                with self._postgres_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT session_json FROM chat_sessions
                            WHERE client_id = %s AND session_id = %s
                            """,
                            (client_id, session_id),
                        )
                        row = cursor.fetchone()
            else:
                with self._sqlite_connection() as connection:
                    row = connection.execute(
                        """
                        SELECT session_json FROM chat_sessions
                        WHERE client_id = ? AND session_id = ?
                        """,
                        (client_id, session_id),
                    ).fetchone()
            return self._decode(row[0]) if row else None
        except (sqlite3.Error, PostgresError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ChatStoreError(f"Could not load conversation: {error}") from error

    def upsert_session(self, client_id: str, session: ChatSession) -> ChatSession:
        """Write one bounded session and prune older sessions for the client.

        Args:
            client_id: Opaque browser identifier used as the ownership boundary.
            session: Pydantic-validated session snapshot.

        Returns:
            The same validated snapshot after persistence.
        """
        session_json = json.dumps(session.model_dump(by_alias=True), separators=(",", ":"))
        if len(session_json.encode("utf-8")) > self._max_session_bytes:
            raise ChatStoreError("Conversation is too large to persist.")
        try:
            if self.is_postgres:
                with self._postgres_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO chat_sessions
                                (client_id, session_id, title, session_json, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (client_id, session_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                session_json = EXCLUDED.session_json,
                                created_at = EXCLUDED.created_at,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                client_id,
                                session.id,
                                session.title,
                                session_json,
                                session.created_at,
                                session.updated_at,
                            ),
                        )
                        self._prune_postgres(cursor, client_id)
            else:
                with self._sqlite_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO chat_sessions
                            (client_id, session_id, title, session_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(client_id, session_id) DO UPDATE SET
                            title = excluded.title,
                            session_json = excluded.session_json,
                            created_at = excluded.created_at,
                            updated_at = excluded.updated_at
                        """,
                        (
                            client_id,
                            session.id,
                            session.title,
                            session_json,
                            session.created_at,
                            session.updated_at,
                        ),
                    )
                    connection.execute(
                        """
                        DELETE FROM chat_sessions
                        WHERE client_id = ? AND session_id NOT IN (
                            SELECT session_id FROM chat_sessions
                            WHERE client_id = ? ORDER BY updated_at DESC LIMIT ?
                        )
                        """,
                        (client_id, client_id, self.max_sessions),
                    )
            return session
        except (sqlite3.Error, PostgresError, ValueError, TypeError) as error:
            raise ChatStoreError(f"Could not save conversation: {error}") from error

    def delete_session(self, client_id: str, session_id: str) -> None:
        """Delete a single session only when it belongs to the client.

        Args:
            client_id: Opaque browser identifier used as the ownership boundary.
            session_id: Conversation to remove.
        """
        try:
            if self.is_postgres:
                with self._postgres_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM chat_sessions WHERE client_id = %s AND session_id = %s",
                            (client_id, session_id),
                        )
            else:
                with self._sqlite_connection() as connection:
                    connection.execute(
                        "DELETE FROM chat_sessions WHERE client_id = ? AND session_id = ?",
                        (client_id, session_id),
                    )
        except (sqlite3.Error, PostgresError) as error:
            raise ChatStoreError(f"Could not delete conversation: {error}") from error

    def close(self) -> None:
        """Close the store; connections are short-lived, so no action is required."""

    def _decode(self, value: str) -> ChatSession:
        """Validate one database JSON value as a public session model."""
        return ChatSession.model_validate(json.loads(value))

    def _sqlite_connection(self) -> sqlite3.Connection:
        """Open the local chat database and create parent directories."""
        if not self.database_url.startswith("sqlite:///"):
            raise ChatStoreError("SQLite chat stores must use a sqlite:/// URL.")
        database_path = Path(self.database_url[len("sqlite:///") :])
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _postgres_connection(self):
        """Import psycopg lazily and open a production PostgreSQL connection."""
        try:
            import psycopg
        except ImportError as error:
            raise ChatStoreError(
                "PostgreSQL chat persistence requires the psycopg[binary] dependency."
            ) from error
        return psycopg.connect(self.database_url)

    def _prune_postgres(self, cursor, client_id: str) -> None:
        """Prune old PostgreSQL rows using the same bounded policy as SQLite."""
        cursor.execute(
            """
            DELETE FROM chat_sessions
            WHERE client_id = %s AND session_id NOT IN (
                SELECT session_id FROM chat_sessions
                WHERE client_id = %s ORDER BY updated_at DESC LIMIT %s
            )
            """,
            (client_id, client_id, self.max_sessions),
        )
