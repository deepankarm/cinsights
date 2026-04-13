from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    api_call_count: int = 0
    subagent_tokens: TokenUsage | None = None


class Attribution(BaseModel):
    calculated_at: datetime | None = None
    agent_lines: int = 0
    agent_removed: int = 0
    human_added: int = 0
    human_modified: int = 0
    human_removed: int = 0
    total_committed: int = 0
    total_lines_changed: int = 0
    agent_percentage: float = 0.0
    metric_version: int = 0


class SessionMetrics(BaseModel):
    duration_ms: int | None = None
    turn_count: int | None = None
    context_tokens: int | None = None
    context_window_size: int | None = None


class SessionFilePaths(BaseModel):
    metadata: str
    transcript: str | None = None
    content_hash: str | None = None
    prompt: str


class CommittedMetadata(BaseModel):
    cli_version: str = ""
    checkpoint_id: str
    session_id: str
    strategy: str = ""
    created_at: datetime
    branch: str | None = None
    checkpoints_count: int = 0
    files_touched: list[str] = Field(default_factory=list)
    agent: str | None = None
    model: str = ""
    turn_id: str | None = None
    is_task: bool = False
    tool_use_id: str | None = None
    checkpoint_transcript_start: int = 0
    token_usage: TokenUsage | None = None
    session_metrics: SessionMetrics | None = None
    initial_attribution: Attribution | None = None


class CheckpointSummary(BaseModel):
    cli_version: str = ""
    checkpoint_id: str
    strategy: str = ""
    branch: str | None = None
    checkpoints_count: int = 0
    files_touched: list[str] = Field(default_factory=list)
    sessions: list[SessionFilePaths] = Field(default_factory=list)
    token_usage: TokenUsage | None = None
    combined_attribution: Attribution | None = None
