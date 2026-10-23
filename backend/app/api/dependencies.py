"""Resolve application-owned services through FastAPI dependencies."""

from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from app.services.database import DatabaseService


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
