import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, Relationship, SQLModel


class SessionStatus(StrEnum):
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

    id: str = Field(primary_key=True)  # Phoenix trace_id
    session_id: str | None = Field(default=None, index=True)  # Phoenix session.id
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
    analysis_prompt_tokens: int = 0  # Tokens used by cinsights analysis
    analysis_completion_tokens: int = 0
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)

    tool_calls: list["ToolCall"] = Relationship(back_populates="session")
    insights: list["Insight"] = Relationship(back_populates="session")


class ToolCall(SQLModel, table=True):
    __tablename__ = "tool_call"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
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
    session_id: str = Field(foreign_key="coding_session.id", index=True)
    category: InsightCategory
    title: str
    content: str  # Markdown
    severity: InsightSeverity = InsightSeverity.INFO
    metadata_json: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    session: CodingSession = Relationship(back_populates="insights")


# --- Digest (cross-session analysis) ---


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
    WORKFLOW_PATTERNS = "workflow_patterns"
    AMBITIOUS_WORKFLOWS = "ambitious_workflows"
    FUN_ENDING = "fun_ending"


class Digest(SQLModel, table=True):
    __tablename__ = "digest"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    project_name: str | None = Field(default=None, index=True)
    period_start: datetime
    period_end: datetime
    session_count: int = 0
    stats_json: str | None = None  # Full computed stats snapshot (JSON)
    analysis_prompt_tokens: int = 0  # Tokens used by cinsights digest analysis
    analysis_completion_tokens: int = 0
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
    metadata_json: str | None = None  # Section-specific structured data
    created_at: datetime = Field(default_factory=datetime.utcnow)

    digest: Digest = Relationship(back_populates="sections")
