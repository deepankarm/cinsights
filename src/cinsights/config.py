import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve DB path relative to project root (where pyproject.toml lives)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = f"sqlite:///{_PROJECT_ROOT / 'cinsights.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CINSIGHTS_", env_file=".env", extra="ignore"
    )

    phoenix_endpoint: str = "http://localhost:6006"
    phoenix_project: str = "claude-code"
    database_url: str = _DEFAULT_DB

    anthropic_api_key: str = ""
    anthropic_base_url: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    # JSON string of extra headers, e.g. '{"x-aig-user-id":"foo"}'
    anthropic_extra_headers: str = ""

    host: str = "127.0.0.1"
    port: int = 8100
    static_dir: str = "ui/build"

    def model_post_init(self, __context):
        # Fall back to standard env vars (without CINSIGHTS_ prefix)
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.anthropic_base_url:
            self.anthropic_base_url = os.environ.get("ANTHROPIC_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
