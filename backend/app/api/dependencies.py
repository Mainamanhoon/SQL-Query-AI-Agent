"""Resolve application-owned services through FastAPI dependencies."""

from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from app.services.chat_store import ChatStore
from app.services.database import DatabaseService
from app.services.sql_validation import SQLValidator


def get_graph(request: Request) -> CompiledStateGraph:
    """Return the startup-built graph without constructing request-global services.

    Args:
        request: Current FastAPI request.
    """
    return request.app.state.graph


def get_database(request: Request) -> DatabaseService:
    """Return the application's read-only database service.

    Args:
        request: Current FastAPI request.
    """
    return request.app.state.database


def get_sql_validator(request: Request) -> SQLValidator:
    """Return the startup-built SQLGlot validator used by graph and editor routes.

    Args:
        request: Current request whose application owns the validator.

    Returns:
        Shared schema-aware SQL validator.
    """
    return request.app.state.sql_validator


def get_chat_store(request: Request) -> ChatStore:
    """Return the startup-built server-side conversation store.

    Args:
        request: Current request whose application owns the store.

    Returns:
        Chat persistence interface shared by session and chat routes.
    """
    return request.app.state.chat_store
