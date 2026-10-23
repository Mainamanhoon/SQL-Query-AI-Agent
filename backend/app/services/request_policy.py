"""Early refusal checks; AST validation remains the authoritative SQL boundary."""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


def requests_destructive_operation(message: str) -> bool:
    """Recognize explicit write requests before asking the model to generate SQL.

    Args:
        message: Untrusted user request, possibly containing SQL.

    Returns:
        True for recognized destructive SQL or direct natural-language write requests.
        This heuristic has no database side effects and does not replace AST validation.
    """
    try:
        expressions = sqlglot.parse(message, read="sqlite")
        if any(
            isinstance(node, (exp.DDL, exp.DML, exp.Attach, exp.Detach))
            for expression in expressions
            if expression is not None
            for node in expression.walk()
        ):
            return True
    except SqlglotError:
        pass
    return bool(
        re.search(
            r"\b(drop|delete|truncate|erase|remove|update|insert|alter)\s+"
            r"(all\b|every\b|the\b|table\b|from\b|into\b|users\b|orders\b|products\b|orderitems\b)",
            message,
            re.IGNORECASE,
        )
    )
