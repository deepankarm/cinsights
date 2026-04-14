import json
import logging
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class PromptTemplates:
    """Prompt template filenames."""

    SESSION_SYSTEM = "session_analysis_system.md.j2"
    SESSION_USER = "session_analysis_user.md.j2"
    PROJECT_DETECTION_SYSTEM = "project_detection_system.md.j2"
    PROJECT_DETECTION_USER = "project_detection_user.md.j2"
    DIGEST_NARRATIVE_SYSTEM = "digest_narrative_system.md.j2"
    DIGEST_NARRATIVE_USER = "digest_narrative_user.md.j2"
    DIGEST_ACTIONS_SYSTEM = "digest_actions_system.md.j2"
    DIGEST_ACTIONS_USER = "digest_actions_user.md.j2"
    DIGEST_FORWARD_SYSTEM = "digest_forward_system.md.j2"
    DIGEST_FORWARD_USER = "digest_forward_user.md.j2"


class Paths:
    """Resolved paths used throughout cinsights."""

    project_root: Path = Path(__file__).resolve().parent.parent.parent
    config_dir: Path = Path.home() / ".cinsights"
    config_file: Path = config_dir / "config.json"
    default_db: str = f"sqlite:///{project_root / 'cinsights.db'}"
    templates_dir: Path = Path(__file__).resolve().parent / "prompts" / "templates"
    jinja_env: Environment = Environment(
        loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True
    )


class LLMConfig(BaseModel):
    """LLM provider configuration.

    API keys are NOT stored here — they come from the environment
    (e.g. ANTHROPIC_API_KEY) and the provider SDK reads them automatically.

    Uses pydantic-ai's ``provider:model`` namespace so any provider that
    pydantic-ai supports works with zero code changes.
    """

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    base_url: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls) -> "LLMConfig":
        """Convenience: load just the LLM section from config.json."""
        return AppConfig.load().llm

    def _make_provider(self, provider_name: str):
        """Provider factory that injects base_url and extra headers."""
        from pydantic_ai.providers import infer_provider_class

        provider_cls = infer_provider_class(provider_name)
        kwargs: dict = {}

        if self.extra_headers:
            import httpx

            client_kwargs: dict = {
                "timeout": 120.0,
                "headers": self.extra_headers,
            }
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            kwargs["http_client"] = httpx.AsyncClient(**client_kwargs)
        elif self.base_url:
            kwargs["base_url"] = self.base_url

        return provider_cls(**kwargs)

    def build_model(self):
        """Build a pydantic-ai Model via ``infer_model("provider:model")``."""
        from pydantic_ai.models import infer_model

        model_id = f"{self.provider}:{self.model}"
        return infer_model(model_id, provider_factory=self._make_provider)


class LimitsConfig(BaseModel):
    """Context window and prompt size limits."""

    max_timeline_spans: int = 200
    timeline_head_tail: int = 30
    max_digest_session_summaries: int = 30
    max_digest_session_health: int = 50
    small_project_threshold: int = 5
    min_coverage_per_user_project: int = 2
    min_coverage_per_project: int = 3


class AppConfig(BaseModel):
    """Full ~/.cinsights/config.json model.

    Example::

        {
          "llm": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "extra_headers": {}
          },
          "claude_code_homes": ["~/.claude-work", "~/.claude"],
          "codex_homes": ["~/.codex"],
          "limits": {
            "max_timeline_spans": 200,
            "max_digest_session_summaries": 30
          }
        }
    """

    llm: LLMConfig = Field(default_factory=LLMConfig)
    claude_code_homes: list[str] = Field(default_factory=lambda: ["~/.claude"])
    codex_homes: list[str] = Field(default_factory=lambda: ["~/.codex"])
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    @classmethod
    def load(cls) -> "AppConfig":
        """Load from ~/.cinsights/config.json, falling back to defaults."""
        if Paths.config_file.is_file():
            try:
                data = json.loads(Paths.config_file.read_text())
                if isinstance(data, dict):
                    return cls.model_validate(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read %s: %s", Paths.config_file, e)
        return cls()

    def save(self) -> None:
        """Write config to ~/.cinsights/config.json."""
        Paths.config_dir.mkdir(parents=True, exist_ok=True)
        Paths.config_file.write_text(self.model_dump_json(indent=2, exclude_none=True) + "\n")

    @property
    def resolved_claude_code_homes(self) -> list[Path]:
        return [Path(p).expanduser() for p in self.claude_code_homes if p.strip()]

    @property
    def resolved_codex_homes(self) -> list[Path]:
        return [Path(p).expanduser() for p in self.codex_homes if p.strip()]


class SourceType(StrEnum):
    PHOENIX = "phoenix"
    ENTIREIO = "entireio"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CINSIGHTS_", env_file=".env", extra="ignore")

    phoenix_endpoint: str = "http://localhost:6006"
    phoenix_project: str = "claude-code"
    database_url: str = Paths.default_db

    tenant_id: str = "default"
    agent_type: str = "claude-code"
    source: SourceType = SourceType.PHOENIX
    prompt_version_session: str = "session-v1"
    prompt_version_digest: str = "digest-v1"

    # Sessions with fewer tool calls than this are excluded from the
    # per-session evidence list in digest prompts.
    min_session_tool_count: int = 10

    # Scoring & selective analysis
    budget_mode: str = "balanced"  # frugal (10%), balanced (30%), thorough (50%), all (100%)
    cold_start_sessions: int = 10  # always analyze first N sessions per (user, project)

    # Entireio source config
    entireio_repo_path: str | None = None
    entireio_branch: str = "entire/checkpoints/v1"

    # Local source config (homes configured in ~/.cinsights/config.json)

    host: str = "127.0.0.1"
    port: int = 8100
    static_dir: str = "ui/build"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> AppConfig:
    return AppConfig.load()


@lru_cache
def get_llm_config() -> LLMConfig:
    return get_config().llm
