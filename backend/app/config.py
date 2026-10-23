"""Environment-backed application configuration."""

from pathlib import Path
from typing import List

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration supplied to application services."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: Path = Path("ecommerce.db")
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    query_timeout_seconds: float = Field(default=2, gt=0, le=30)
    query_row_limit: int = Field(default=200, ge=1, le=1000)
    cors_origins: List[str] = ["http://localhost:5173"]
