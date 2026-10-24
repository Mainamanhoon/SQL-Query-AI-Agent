"""Verify the database boundary independently of prompts and AST validation."""

import sqlite3
from pathlib import Path

import pytest

from app.services.database import DatabaseService
from seed_db import seed_database


def test_seed_is_repeatable_and_preserves_data(database_path: Path) -> None:
    """Reseeding preserves existing rows and all declared foreign keys are valid."""
    assert seed_database(database_path) is False
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        counts = [
            connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ["Users", "Products", "Orders", "OrderItems"]
        ]
    assert counts == [6, 6, 6, 10]


def test_schema_contains_columns_and_relationships(database: DatabaseService) -> None:
    """Metadata includes complete DDL and the relationships needed for join validation."""
    assert len(database.schema.tables) == 4
    assert database.schema.tables["Users"].columns["state"] == "TEXT"
    assert database.schema.tables["Orders"].foreign_keys[0].referenced_table == "Users"
    assert "CREATE TABLE OrderItems" in database.schema.ddl


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE Users",
        "DELETE FROM Users",
        "UPDATE Users SET state = 'x'",
        "INSERT INTO Users VALUES (7, 'x', 'x', 'x', 'x')",
        "PRAGMA table_info(Users)",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT * FROM sqlite_master",
        "SELECT load_extension('bad')",
    ],
)
def test_authorizer_denies_unapproved_actions(database: DatabaseService, sql: str) -> None:
    """The database rejects forbidden actions even if the AST boundary is bypassed."""
    with pytest.raises(sqlite3.DatabaseError):
        database.execute(sql)
    assert len(database.execute("SELECT id FROM Users").rows) == 6


def test_authorizer_allows_read_only_aggregates(database: DatabaseService) -> None:
    """Safe aggregate functions work without permitting writes or extensions."""
    result = database.execute(
        "SELECT state, COUNT(*) AS user_count FROM Users GROUP BY state ORDER BY state"
    )
    assert result.columns == ["state", "user_count"]
    assert result.rows == [["California", 3], ["New York", 1], ["Texas", 1], ["Washington", 1]]


def test_result_limit_preserves_columns(database_path: Path) -> None:
    """Results remain bounded and advertise truncation rather than silently losing rows."""
    database = DatabaseService(database_path, timeout_seconds=1, row_limit=2)
    result = database.execute("SELECT id, name FROM Users ORDER BY id")
    assert result.columns == ["id", "name"]
    assert len(result.rows) == 2
    assert result.truncated


def test_progress_handler_interrupts_expensive_query(database_path: Path) -> None:
    """A large Cartesian product is interrupted by the execution deadline."""
    database = DatabaseService(database_path, timeout_seconds=0.001, row_limit=1)
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        database.execute(
            "SELECT a.id FROM OrderItems a, OrderItems b, OrderItems c, OrderItems d, "
            "OrderItems e, OrderItems f, OrderItems g ORDER BY a.id + b.id + c.id + d.id"
        )
