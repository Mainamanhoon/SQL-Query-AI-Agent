"""Adversarial validation and scope-aware schema checks."""

import pytest

from app.agent.nodes import AgentDependencies, validation_node
from app.api.routes import initial_state
from app.models.chat import ChatRequest
from app.services.database import DatabaseService
from app.services.request_policy import requests_destructive_operation
from app.services.sql_validation import SQLValidationError, SQLValidator


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE Users",
        "DELETE FROM Users",
        "UPDATE Users SET state='x'",
        "INSERT INTO Users SELECT * FROM Users",
        "ALTER TABLE Users ADD COLUMN hacked TEXT",
        "TRUNCATE TABLE Users",
        "SELECT * FROM Users; DROP TABLE Users",
        "SELECT * FROM Users; SELECT * FROM Products",
        "PRAGMA writable_schema=ON",
        "ATTACH DATABASE 'other.db' AS other",
        "EXPLAIN SELECT * FROM Users",
        "SELECT * INTO backup FROM Users",
        "SELECT * FROM Users UNION SELECT * FROM Users",
        "WITH x AS (DELETE FROM Users RETURNING *) SELECT * FROM x",
        "WITH x AS (SELECT * FROM Users) DELETE FROM Users",
        "SELECT * FROM main.Users",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM read_csv('secret.csv')",
        "SELECT * FROM Missing",
        "SELECT password FROM Users",
        "SELECT u.missing FROM Users u",
        "SELECT id FROM Users u JOIN Orders o ON u.id=o.user_id",
        "SELECT u.name FROM Users u JOIN Orders o ON u.id=o.id",
        "SELECT u.name FROM Users u JOIN Orders o ON u.id=o.user_id OR 1=1",
        "SELECT u.name FROM Users u JOIN Orders o ON NOT (u.id=o.user_id)",
        "SELECT u.name FROM Users u JOIN Orders o ON CASE WHEN u.id=o.user_id THEN 0 ELSE 1 END",
        "SELECT * FROM Users CROSS JOIN Products",
        "SELECT * FROM Users -- benign\n; /* hidden */ DROP TABLE Orders",
        "SELECT * FROM Users WHERE (",
        "",
        ";",
        "```sql\nSELECT * FROM Users\n```",
    ],
)
def test_rejects_unsafe_or_invalid_sql(database: DatabaseService, sql: str) -> None:
    """No unsafe command, hallucinated identifier, or invalid relationship is accepted."""
    with pytest.raises(SQLValidationError):
        SQLValidator(database.schema).validate(sql)


@pytest.mark.parametrize(
    "sql, row_count",
    [
        ("SELECT * FROM Users", 6),
        ("SELECT name FROM Users WHERE state='California'", 3),
        ("SELECT u.name FROM Users u JOIN Orders o ON u.id=o.user_id", 6),
        (
            "SELECT u.name FROM Users u JOIN Orders o ON o.user_id=u.id "
            "JOIN OrderItems i ON i.order_id=o.id",
            10,
        ),
        ("WITH ca AS (SELECT id, name FROM Users WHERE state='California') SELECT name FROM ca", 3),
        ("SELECT x.name FROM (SELECT name FROM Users) x", 6),
        ("SELECT name FROM Users u WHERE EXISTS (SELECT 1 FROM Orders o WHERE o.user_id=u.id)", 5),
        ("SELECT 'DROP TABLE Users; --' AS note FROM Users LIMIT 1", 1),
        ("SELECT name AS customer FROM Users ORDER BY customer", 6),
        ("SELECT p.price_cents / 100.0 AS price FROM Products p", 6),
        ("SELECT state, COUNT(*) AS user_count FROM Users GROUP BY state", 4),
        ("SELECT CAST(price_cents AS REAL) FROM Products", 6),
        ("SELECT CURRENT_DATE FROM Users", 6),
        ("SELECT CASE WHEN state='California' THEN 1 ELSE 0 END FROM Users", 6),
    ],
)
def test_valid_queries_resolve_scopes_and_execute(
    database: DatabaseService, sql: str, row_count: int
) -> None:
    """Valid aliases, CTEs, correlated subqueries, and FK joins remain usable."""
    validated = SQLValidator(database.schema).validate(sql)
    assert len(database.execute(validated).rows) == row_count


def test_validation_node_records_error_and_increments_once(database: DatabaseService) -> None:
    """The node exposes failed SQL context for repair without executing the candidate."""
    state = initial_state(ChatRequest(message="Show users"))
    state["generated_sql"] = "SELECT * FROM Users; DROP TABLE Users"
    dependencies = AgentDependencies(database, SQLValidator(database.schema), None)  # type: ignore[arg-type]
    update = validation_node(state, dependencies)
    assert update["is_valid"] is False
    assert update["retry_count"] == 1
    assert "Exactly one" in update["error_msg"]


@pytest.mark.parametrize(
    "message",
    [
        "Delete user 1",
        "Please drop the users table",
        "Set every customer's state to Texas",
        "Create an index on Users.state",
        "Modify the data for this customer",
    ],
)
def test_destructive_requests_are_rejected_before_generation(message: str) -> None:
    """Natural-language write requests cannot rely on the model to refuse them."""
    assert requests_destructive_operation(message)


@pytest.mark.parametrize(
    "message",
    [
        "Create a query to list users",
        "Optimize this query by removing unnecessary joins",
    ],
)
def test_read_only_sql_requests_are_not_misclassified_as_destructive(message: str) -> None:
    """Query composition and optimization wording remains allowed."""
    assert not requests_destructive_operation(message)
