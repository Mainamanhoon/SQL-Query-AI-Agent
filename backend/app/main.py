"""Application composition root; all integrations are created in lifespan."""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent.graph import build_graph
from app.agent.nodes import AgentDependencies
from app.api.routes import router
from app.config import Settings
from app.services.database import DatabaseService
from app.services.llm import HTTPChatModel, LanguageModel
from app.services.sql_validation import SQLValidator


def create_app(
    settings: Optional[Settings] = None, model: Optional[LanguageModel] = None
) -> FastAPI:
    """Build the FastAPI application with optional injected configuration/model.

    Args:
        settings: Explicit settings, or load environment settings at startup.
        model: Optional alternate model implementation for tests or integrations.

    Returns:
        Application with lifecycle-owned services and HTTP routes.
    """
    configuration = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize services and close the shared HTTP transport on shutdown.

        Args:
            application: FastAPI instance receiving lifecycle-owned dependencies.

        Yields:
            Control while the application serves requests; reads schema at startup.
        """
        database = DatabaseService(
            configuration.database_path,
            configuration.query_timeout_seconds,
            configuration.query_row_limit,
        )
        async with httpx.AsyncClient(timeout=configuration.llm_timeout_seconds) as client:
            language_model = model or HTTPChatModel(
                client,
                configuration.llm_api_key.get_secret_value(),
                configuration.llm_base_url,
                configuration.llm_model,
                configuration.llm_max_tokens,
            )
            application.state.database = database
            application.state.model_configured = bool(
                model or (configuration.llm_api_key.get_secret_value() and configuration.llm_model)
            )
            application.state.graph = build_graph(
                AgentDependencies(database, SQLValidator(database.schema), language_model)
            )
            yield

    application = FastAPI(title="QueryDesk API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.include_router(router, prefix="/api", include_in_schema=False)
    if configuration.frontend_dist is not None:
        application.mount("/", StaticFiles(directory=configuration.frontend_dist, html=True))
    return application
