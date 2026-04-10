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

    # Multi-tenant boundary. CINSIGHTS_TENANT_ID env var picks the tenant for
    # the running process; multiple machines/users can write to the same DB
    # under different tenant_ids.
    tenant_id: str = "default"
    # Default coding agent + observability source for new sessions. Both can be
    # overridden per-row later when we add multi-agent / multi-source ingestion.
    agent_type: str = "claude-code"
    source: str = "phoenix"
    # Prompt versions stamped on insights/digests so we can iterate prompts
    # without orphaning historical analyses.
    prompt_version_session: str = "session-v1"
    prompt_version_digest: str = "digest-v1"

    anthropic_api_key: str = ""
    anthropic_base_url: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    # JSON string of extra headers, e.g. '{"x-aig-user-id":"foo"}'
    anthropic_extra_headers: str = ""

    # Lightweight model for the per-session project-detection LLM call.
    # Cheap and cost-sensitive — defaults to Haiku 4.5. Reuses the
    # anthropic_api_key / base_url / extra_headers above.
    project_detection_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    # Sessions with fewer tool calls than this are excluded from the
    # per-session evidence list in digest prompts (they still count toward
    # aggregate stats like tool distribution and token totals).
    min_session_tool_count: int = 10

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
