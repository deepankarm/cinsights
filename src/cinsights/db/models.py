import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, Relationship, SQLModel


class SessionStatus(StrEnum):
    INDEXED = "indexed"
    PENDING = "pending"
    ANALYZED = "analyzed"
    FAILED = "failed"


class InsightCategory(StrEnum):
    SUMMARY = "summary"
    FRICTION = "friction"
    WIN = "win"
    RECOMMENDATION = "recommendation"
    PATTERN = "pattern"
    SKILL_PROPOSAL = "skill_proposal"


class InsightSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CodingSession(SQLModel, table=True):
    __tablename__ = "coding_session"

    id: str = Field(primary_key=True)  # source-specific session key
    tenant_id: str = Field(default="default", index=True)  # multi-tenant boundary
    source: str = Field(default="local")  # observability backend
    agent_type: str = Field(default="claude-code")  # coding agent identity
    session_id: str | None = Field(default=None, index=True)  # source-native session grouping key
    user_id: str | None = Field(default=None, index=True)  # user.id from spans
    project_name: str | None = Field(default=None, index=True)  # project.name from spans
    start_time: datetime
    end_time: datetime | None = None
    model: str | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    span_count: int = 0  # Track span count for change detection
    last_span_time: datetime | None = None  # Track latest span for change detection
    context_growth_json: str | None = None  # [{turn, prompt_tokens, completion_tokens}]
    metadata_json: str | None = None  # Source-specific rich data (cache tokens, attribution, etc.)

    # Tier 0 quality metrics (computed during indexing, zero LLM cost)
    read_edit_ratio: float | None = None
    edits_without_read_pct: float | None = None
    research_mutation_ratio: float | None = None
    write_vs_edit_pct: float | None = None
    error_rate: float | None = None
    repeated_edits_count: int | None = None
    subagent_spawn_rate: float | None = None
    tokens_per_useful_edit: float | None = None
    context_pressure_score: float | None = None
    turn_count: int | None = None
    tool_calls_per_turn: float | None = None

    # Token efficiency signals (computed during indexing)
    error_retry_sequences: int | None = None
    context_resets: int | None = None
    duplicate_read_count: int | None = None

    # Token efficiency — waste metrics (computed during indexing, zero LLM cost)
    compaction_cycle_waste: int | None = None  # tokens in growth-reset cycles
    floor_drift_score: float | None = None  # 0-1, growing post-compaction floor
    interrupted_turn_waste: int | None = None  # prompt tokens for interrupted turns
    repeated_edit_waste: int | None = None  # thrashing cost
    failed_retry_waste: int | None = None  # error retry cost
    efficiency_score: float | None = None  # 0-100 composite score

    # Task-based metrics (computed during analyze, LLM)
    task_count: int | None = None  # number of detected tasks
    estimated_task_waste_tokens: int | None = None  # total compact-at-boundary waste

    interrupt_count: int | None = None
    agent_version: str | None = None
    effort_level: str | None = None  # low / medium / high / max
    adaptive_thinking_disabled: bool | None = None

    # Scoring
    interestingness_score: float | None = None
    skip_reason: str | None = None
    estimated_analysis_tokens: int | None = None  # Estimated prompt tokens for LLM analysis

    analysis_prompt_tokens: int = 0  # Tokens used by cinsights analysis
    analysis_completion_tokens: int = 0
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)

    tool_calls: list["ToolCall"] = Relationship(back_populates="session")
    insights: list["Insight"] = Relationship(back_populates="session")
    tasks: list["Task"] = Relationship(back_populates="session")


class Task(SQLModel, table=True):
    """A coherent unit of work within a session, detected by LLM segmentation."""

    __tablename__ = "task"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    session_id: str = Field(foreign_key="coding_session.id", index=True)
    task_number: int  # 1-indexed within session
    name: str  # 3-8 word concise name
    description: str  # 1-2 sentences
    start_turn: int
    end_turn: int
    turn_count: int
    prompt_tokens_total: int = 0  # total prompt tokens across turns in this task
    completion_tokens_total: int = 0
    context_at_start: int | None = None  # context window size at first turn
    estimated_waste_tokens: int | None = None  # compact-at-boundary waste
    created_at: datetime = Field(default_factory=datetime.utcnow)

    session: CodingSession = Relationship(back_populates="tasks")


class Theme(SQLModel, table=True):
    """A coherent work area within a project, extracted from grouped tasks via LLM."""

    __tablename__ = "theme"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    project_name: str = Field(index=True)
    name: str  # e.g. "Checkpoints V2 — Data model, storage, and migration"
    summary: str  # 1-2 sentences explaining the work area
    total_tokens: int = 0
    task_count: int = 0
    first_date: datetime | None = None  # earliest member-task start_time
    last_date: datetime | None = None  # latest member-task start_time
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ThemeTask(SQLModel, table=True):
    """Junction: one task belongs to exactly one theme by extraction rules,
    but the relation stays many-to-many for forward flexibility (re-extraction,
    splits, manual reassignment)."""

    __tablename__ = "theme_task"

    theme_id: str = Field(foreign_key="theme.id", primary_key=True)
    task_id: str = Field(foreign_key="task.id", primary_key=True)
    tenant_id: str = Field(default="default", index=True)


class ToolCall(SQLModel, table=True):
    __tablename__ = "tool_call"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)  # denormalized from session
    session_id: str = Field(foreign_key="coding_session.id", index=True)
    span_id: str
    tool_name: str = Field(index=True)
    input_value: str | None = None
    output_value: str | None = None
    duration_ms: float | None = None
    success: bool = True
    timestamp: datetime

    session: CodingSession = Relationship(back_populates="tool_calls")


class Insight(SQLModel, table=True):
    __tablename__ = "insight"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)  # denormalized from session
    session_id: str = Field(foreign_key="coding_session.id", index=True)
    category: InsightCategory
    title: str
    content: str  # Markdown
    severity: InsightSeverity = InsightSeverity.INFO
    prompt_version: str | None = None  # set when written; lets us iterate prompts safely
    metadata_json: str | None = None
    cluster_label: str | None = Field(
        default=None, index=True
    )  # canonical label set during digest clustering
    created_at: datetime = Field(default_factory=datetime.utcnow)

    session: CodingSession = Relationship(back_populates="insights")


class SessionDailyTrend(SQLModel, table=True):
    __tablename__ = "session_daily_trend"

    id: str = Field(primary_key=True)  # "{date}:{user_id}:{project_name}"
    date: str = Field(index=True)  # ISO date YYYY-MM-DD
    user_id: str = Field(index=True)
    project_name: str | None = Field(default=None, index=True)
    tenant_id: str = Field(default="default", index=True)

    session_count: int = 0
    indexed_count: int = 0
    analyzed_count: int = 0
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0

    avg_read_edit_ratio: float | None = None
    avg_edits_without_read_pct: float | None = None
    avg_research_mutation_ratio: float | None = None
    avg_write_vs_edit_pct: float | None = None
    avg_error_rate: float | None = None

    avg_session_duration_ms: float | None = None
    avg_tool_calls_per_turn: float | None = None

    agent_distribution_json: str | None = None

    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SessionBaseline(SQLModel, table=True):
    __tablename__ = "session_baseline"

    id: str = Field(primary_key=True)  # "{user_id}:{project_name}"
    user_id: str = Field(index=True)
    project_name: str | None = Field(default=None, index=True)
    tenant_id: str = Field(default="default")

    session_count: int = 0
    avg_turns: float = 0
    avg_tool_count: float = 0
    avg_read_edit_ratio: float = 0
    avg_edits_without_read_pct: float = 0
    avg_error_rate: float = 0
    avg_duration_ms: float = 0
    avg_research_mutation_ratio: float = 0
    avg_write_vs_edit_pct: float = 0
    tool_distribution_json: str | None = None

    last_updated: datetime = Field(default_factory=datetime.utcnow)


class DigestStatus(StrEnum):
    PENDING = "pending"
    COMPUTING_STATS = "computing_stats"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    FAILED = "failed"


class DigestSectionType(StrEnum):
    AT_A_GLANCE = "at_a_glance"
    WORK_AREAS = "work_areas"
    DEVELOPER_PERSONA = "developer_persona"
    IMPRESSIVE_WINS = "impressive_wins"
    FRICTION_ANALYSIS = "friction_analysis"
    CLAUDE_MD_SUGGESTIONS = "claude_md_suggestions"
    FEATURE_RECOMMENDATIONS = "feature_recommendations"
    RECOMMENDATIONS = "recommendations"
    WORKFLOW_PATTERNS = "workflow_patterns"
    AMBITIOUS_WORKFLOWS = "ambitious_workflows"
    STOP_HOOK_SUGGESTIONS = "stop_hook_suggestions"
    TASK_ANALYSIS = "task_analysis"
    EFFICIENCY_INSIGHTS = "efficiency_insights"
    # Legacy values kept for SQLite CHECK constraint compatibility.
    FUN_ENDING = "fun_ending"


class Digest(SQLModel, table=True):
    __tablename__ = "digest"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)  # multi-tenant boundary
    user_id: str | None = Field(default=None, index=True)
    project_name: str | None = Field(default=None, index=True)
    period_start: datetime
    period_end: datetime
    session_count: int = 0
    stats_json: str | None = None  # Full computed stats snapshot (JSON)
    analysis_prompt_tokens: int = 0  # Tokens used by cinsights digest analysis
    analysis_completion_tokens: int = 0
    analysis_model: str | None = None  # LLM model used for digest analysis
    status: DigestStatus = DigestStatus.PENDING
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    sections: list["DigestSection"] = Relationship(back_populates="digest")


class DigestSection(SQLModel, table=True):
    __tablename__ = "digest_section"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    digest_id: str = Field(foreign_key="digest.id", index=True)
    section_type: DigestSectionType
    title: str
    content: str  # Markdown
    order: int = 0
    prompt_version: str | None = None  # set when written; lets us iterate prompts safely
    metadata_json: str | None = None  # Section-specific structured data
    created_at: datetime = Field(default_factory=datetime.utcnow)

    digest: Digest = Relationship(back_populates="sections")


class ScopeStats(SQLModel, table=True):
    """Pre-computed stats per user or project scope. Updated after analyze."""

    __tablename__ = "scope_stats"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    scope_type: str = Field(index=True)  # "user" or "project"
    scope_value: str = Field(index=True)  # user_id or project_name
    stats_json: str | None = None
    session_count: int = 0
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class RefreshRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class RefreshRunCommand(StrEnum):
    REFRESH = "refresh"
    ANALYZE = "analyze"
    DIGEST = "digest"


class LLMCallKind(StrEnum):
    SESSION_ANALYSIS = "session_analysis"
    PROJECT_DETECTION = "project_detection"
    DIGEST_NARRATIVE = "digest_narrative"
    DIGEST_ACTIONS = "digest_actions"
    DIGEST_FORWARD = "digest_forward"
    TASK_SEGMENTATION = "task_segmentation"
    THEME_EXTRACTION = "theme_extraction"


class LLMCallScopeType(StrEnum):
    SESSION = "session"
    DIGEST = "digest"
    UNKNOWN = "unknown"


class LLMCallStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class LLMCallLog(SQLModel, table=True):
    """Per-call LLM accounting. RefreshRun keeps the run-level rollup."""

    __tablename__ = "llm_call_log"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    call_kind: LLMCallKind = Field(index=True)
    scope_type: LLMCallScopeType = LLMCallScopeType.UNKNOWN
    scope_id: str | None = Field(default=None, index=True)
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    duration_ms: float | None = None
    status: LLMCallStatus = LLMCallStatus.SUCCESS
    error_message: str | None = None
    dollar_cost: float | None = None
    schema_version: int = 1
    metadata_json: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class RefreshRun(SQLModel, table=True):
    """Self-observability for cinsights itself.

    One row per analyze/digest/refresh invocation. Captures wall-clock duration,
    LLM token spend, and DB size so we can detect when migration triggers fire
    (rollups, Postgres) without guessing.
    """

    __tablename__ = "refresh_run"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    command: RefreshRunCommand
    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    completed_at: datetime | None = None
    status: RefreshRunStatus = RefreshRunStatus.RUNNING
    sessions_analyzed: int = 0
    digests_generated: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    db_size_bytes: int | None = None
    wall_seconds: float | None = None
    error_message: str | None = None
    metadata_json: str | None = None
