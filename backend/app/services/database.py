"""Read-only execution with SQLite authorizer and bounded resource usage."""

import sqlite3
from pathlib import Path
from time import monotonic
from typing import Callable, Optional

from app.models.database import DatabaseSchema, QueryResults
from app.services.schema import read_schema

Authorizer = Callable[[int, Optional[str], Optional[str], Optional[str], Optional[str]], int]


class DatabaseService:
    """Own short-lived, read-only connections; never share connections across requests."""

    def __init__(self, database_path: Path, timeout_seconds: float, row_limit: int) -> None:
        """Store injected database settings and load its trusted schema.

        Args:
            database_path: Existing seeded SQLite database.
            timeout_seconds: Maximum query runtime in seconds.
            row_limit: Maximum number of result rows returned.

        Side Effects:
            Reads database metadata once; performs no writes.
        """
        if timeout_seconds <= 0 or row_limit < 1:
            raise ValueError("Timeout and row limit must be positive.")
        self.database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
        self.timeout_seconds = timeout_seconds
        self.row_limit = row_limit
        self.schema: DatabaseSchema = read_schema(database_path)

    def _authorizer(self) -> Authorizer:
        """Build a deny-by-default callback for application-table reads only.

        Returns:
            A callback allowing only SELECT and READ actions, without side effects.
        """
        table_names = {name.casefold() for name in self.schema.tables}

        def authorize(
            action: int,
            table_name: Optional[str],
            column_name: Optional[str],
            database_name: Optional[str],
            source: Optional[str],
        ) -> int:
            """Authorize one SQLite action without changing the database.

            Args:
                action: SQLite action code.
                table_name: Accessed table or first action argument.
                column_name: Accessed column or second action argument.
                database_name: Database containing the accessed object.
                source: Trigger or view causing the access, if any.

            Returns:
                SQLITE_OK for approved reads, otherwise SQLITE_DENY.
            """
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if (
                action == sqlite3.SQLITE_READ
                and (database_name == "main" or (database_name is None and column_name == ""))
                and (table_name or "").casefold() in table_names
            ):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        return authorize

    def execute(self, validated_sql: str) -> QueryResults:
        """Execute validated SQL with an independent database-level safety boundary.

        Args:
            validated_sql: Single SELECT that passed AST and schema validation.

        Returns:
            Column names, bounded positional rows, timing, and truncation status.

        Raises:
            sqlite3.DatabaseError: SQL is rejected, fails, or exceeds its deadline.

        Side Effects:
            Opens and closes a read-only connection; never modifies database data.
        """
        started_at = monotonic()
        connection = sqlite3.connect(self.database_uri, uri=True, timeout=self.timeout_seconds)
        try:
            if hasattr(connection, "enable_load_extension"):
                connection.enable_load_extension(False)
            connection.set_authorizer(self._authorizer())

            def deadline_exceeded() -> int:
                """Return nonzero to interrupt execution after the injected deadline."""
                return int(monotonic() - started_at >= self.timeout_seconds)

            connection.set_progress_handler(deadline_exceeded, 1000)
            cursor = connection.execute(validated_sql)
            rows = cursor.fetchmany(self.row_limit + 1)
            return QueryResults(
                columns=[description[0] for description in cursor.description or []],
                rows=[list(row) for row in rows[: self.row_limit]],
                truncated=len(rows) > self.row_limit,
                elapsed_ms=round((monotonic() - started_at) * 1000, 2),
                row_limit=self.row_limit,
            )
        finally:
            connection.close()
