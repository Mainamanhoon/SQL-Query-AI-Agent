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
    write_verbs = (
        r"drop|delete|truncate|erase|remove|update|insert|alter|replace|upsert|merge|"
        r"purge|wipe|clear|write|save|persist"
    )
    data_targets = (
        r"all|every|data|value|values|row|rows|record|records|table|tables|database|schema|"
        r"column|columns|index|user|users|customer|customers|order|orders|product|products|"
        r"orderitems"
    )
    if re.search(
        rf"\b(?:{write_verbs})\b[\s\S]{{0,100}}\b(?:{data_targets})\b",
        message,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\bcreate\b[\s\S]{0,40}\b(?:table|index|view|trigger|database|schema)\b",
        message,
        re.IGNORECASE,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:modify|change|set)\b[\s\S]{0,100}\b(?:row|record|user|users|"
            r"customer|customers|order|orders|product|products|state|column|table|schema)\b",
            message,
            re.IGNORECASE,
        )
    )
