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
    start_time: datetime
    end_time: datetime | None = None
    model: str | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    status: SessionStatus = SessionStatus.PENDING
    project_name: str | None = None
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
