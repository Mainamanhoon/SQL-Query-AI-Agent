"""Vercel entrypoint for the QueryDesk FastAPI application."""

from app.main import create_app

app = create_app()
