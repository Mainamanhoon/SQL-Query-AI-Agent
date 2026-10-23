"""Isolated database fixtures."""

from pathlib import Path

import pytest

from app.services.database import DatabaseService
from seed_db import seed_database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Seed a fresh database within the test's temporary directory."""
    destination = tmp_path / "ecommerce.db"
    seed_database(destination)
    return destination


@pytest.fixture
def database(database_path: Path) -> DatabaseService:
    """Return an isolated database service with production safety controls."""
    return DatabaseService(database_path, timeout_seconds=1, row_limit=200)
