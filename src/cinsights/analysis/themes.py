"""Theme extraction — group a project's tasks into named work areas via LLM.

A Theme is a sustained effort on the same feature, bug area, refactor, or
initiative — typically spanning multiple sessions and possibly multiple
developers. One LLM call per project produces all themes for that project,
running as part of the digest pipeline for project-scoped digests.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy import select

from cinsights.analysis import LLMAnalyzer
from cinsights.db.models import (
    CodingSession,
    LLMCallKind,
    LLMCallScopeType,
    Task,
    Theme,
    ThemeTask,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


# --- Pydantic models (LLM output schema) ---


class ThemeItem(BaseModel):
    name: str = Field(
        description="3-8 words. Lead with the SUBJECT (feature/component/area), not an activity verb."
    )
    summary: str = Field(description="1-2 sentences explaining what this work is about.")
    task_ids: list[int] = Field(description="Sequential task IDs (T<n>) that belong to this theme.")


class ThemeExtractionResult(BaseModel):
    themes: list[ThemeItem]


# --- Prompts (kept inline; one prompt, no template variables beyond task list) ---


SYSTEM_PROMPT = """\
You are analyzing a coding team's task corpus to identify the high-level THEMES of work.

A THEME is a sustained effort on the same feature, bug area, refactor, or
initiative — typically spanning multiple sessions and possibly multiple developers.
A theme is NOT an activity type (review, debug, commit) — it's the WORK PRODUCT
or the AREA OF FOCUS.

Goal: someone scanning these themes should immediately understand what the team
has been building / fixing / exploring, who's involved, and where time is going.

Rules:
- EVERY task must be assigned to exactly one theme. No orphans, no duplicates.
- Theme size is fully flexible — themes of size 1 are valid. A truly one-off
  task gets its own single-task theme named after its actual subject.
- Do NOT create a generic "Other", "Miscellaneous", "Various", or "Misc"
  catch-all theme. Every theme name must refer to a specific subject
  (feature, component, file, bug area). If a task doesn't fit an existing
  theme, give it its own theme named after what the task is actually about.
- Themes can be cross-developer or solo. Solo is fine if a single dev owned
  a feature. Look at the FULL set of tasks; a theme often groups work
  that happened across multiple sessions and weeks.

Naming rules — most important:
- Lead with the SUBJECT (feature/component/area), not the activity verb.
- Be specific. The name should answer "what was the team working on", not
  "what kind of activity".
- Activity-only names are FORBIDDEN.

Good theme names — illustrative shape only. These are HYPOTHETICAL examples
from unrelated projects (auth, payments, mobile, reporting) — do NOT use these
subjects in your output unless the corpus actually contains that work:
  - "Auth service — JWT migration + role middleware refactor"
  - "Mobile push notifications — APNs / FCM unification"
  - "Checkout funnel — A/B test rollout for new layout"
  - "Reporting CSV exports — performance regression fixes"
  - "Webhook delivery retry — exponential backoff + DLQ"
  - "Onboarding flow — drop-off analysis and UX fixes"
  - "Image upload pipeline — switch to S3 presigned URLs"
  - "Admin dashboard — search + filtering improvements"

Bad theme names — REJECT and rewrite:
  - "Code reviews"          (activity, not subject)
  - "Bug fixes"             (no subject)
  - "Various improvements"  (vacuous)
  - "Testing"               (activity)
  - "Refactoring"           (activity)
  - "PR work"               (activity, not subject)

Group by noun, not by verb. When a task name contains both an activity verb
and a subject (e.g. "<verb> of <subject>" or "<subject> <verb>"), the
SUBJECT determines which theme it belongs to. Two tasks that share a verb
but have different subjects belong to different themes — never bundle them
just because the verb matches.

Pull theme names from THIS corpus — the actual feature names, components,
and bug areas mentioned in the task names and descriptions. The examples
above show shape only; the corpus tells you the content.

Final check before returning:
- Does any theme name describe an activity (verb) instead of a subject
  (noun)? → rewrite or split.
- Does any theme name use generic catch-all words (other, misc, various,
  miscellaneous)? → forbidden. Rename to refer to the actual subject.
- Is every task ID in exactly one theme's task_ids list? → verify uniqueness.
"""

USER_PROMPT_TEMPLATE = """\
Here is a corpus of {n_tasks} tasks from project '{project}'. Each line shows:

`T<id> | <user> | <YYYY-MM-DD> | <task name> — <one-sentence description>`

Extract themes per the rules. Aim for as many themes as the work naturally
requires — single-task themes are valid for genuine one-offs. Do NOT
create an "Other"/"Misc" catch-all. Return every task ID assigned to
exactly one specifically-named theme.

---
{tasks}
"""


# --- Loader / formatter helpers ---


def _short_user(uid: str | None) -> str:
    if not uid:
        return "?"
    return uid.split("@")[0]


def _first_sentence(text: str | None, max_chars: int = 200) -> str:
    if not text:
        return ""
    text = text.strip()
    for sep in (". ", "? ", "! "):
        if sep in text:
            return text.split(sep, 1)[0][:max_chars]
    return text[:max_chars]


def _format_task_line(
    seq_id: int, task_name: str, description: str, user: str | None, start_time: datetime | None
) -> str:
    user_short = _short_user(user)[:20]
    date = start_time.strftime("%Y-%m-%d") if start_time else "?"
    return f"T{seq_id:>4d} | {user_short:20s} | {date} | {task_name} — {_first_sentence(description, 150)}"


# --- Loaded task structure ---


class _LoadedTask(BaseModel):
    """One row from the project task corpus, with sequential id used in the prompt."""

    seq_id: int  # 0-indexed prompt id (T<seq_id>)
    db_id: str  # Task.id
    name: str
    description: str
    prompt_tokens: int
    completion_tokens: int
    user_id: str | None
    start_time: datetime | None


# --- Analyzer ---


class ThemeAnalyzer(LLMAnalyzer):
    """Single LLM call per project — extracts themes from grouped tasks."""

    MIN_TASKS = 5  # below this, theme extraction is noise
    MAX_TOKENS = 32768  # headroom for large theme lists on big corpora

    async def load_tasks(
        self,
        db: AsyncSession,
        project_name: str,
        tenant_id: str = "default",
    ) -> list[_LoadedTask]:
        """Load all tasks for a project, ordered by session start_time then task_number."""
        r = await db.execute(
            select(
                Task.id,
                Task.name,
                Task.description,
                Task.prompt_tokens_total,
                Task.completion_tokens_total,
                CodingSession.user_id,
                CodingSession.start_time,
            )
            .join(CodingSession, CodingSession.id == Task.session_id)
            .where(CodingSession.project_name == project_name)
            .where(Task.tenant_id == tenant_id)
            .order_by(CodingSession.start_time, Task.task_number)
        )
        rows = r.all()
        return [
            _LoadedTask(
                seq_id=i,
                db_id=row[0],
                name=row[1],
                description=row[2] or "",
                prompt_tokens=row[3] or 0,
                completion_tokens=row[4] or 0,
                user_id=row[5],
                start_time=row[6],
            )
            for i, row in enumerate(rows)
        ]

    async def extract(
        self,
        project_name: str,
        tasks: list[_LoadedTask],
        *,
        digest_id: str | None = None,
    ) -> tuple[ThemeExtractionResult, int, int]:
        """Run the single LLM call. Returns (result, prompt_tokens, completion_tokens)."""
        task_lines = "\n".join(
            _format_task_line(t.seq_id, t.name, t.description, t.user_id, t.start_time)
            for t in tasks
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            n_tasks=len(tasks), project=project_name, tasks=task_lines
        )
        logger.info(
            "Theme extraction: project=%s tasks=%d prompt_chars=%d",
            project_name,
            len(tasks),
            len(user_prompt),
        )
        result, p_tok, c_tok = await self._run_llm(
            ThemeExtractionResult,
            SYSTEM_PROMPT,
            user_prompt,
            call_kind=LLMCallKind.THEME_EXTRACTION,
            scope_type=LLMCallScopeType.DIGEST if digest_id else LLMCallScopeType.UNKNOWN,
            scope_id=digest_id,
            max_tokens=self.MAX_TOKENS,
        )
        return result, p_tok, c_tok


# --- Validation + storage ---


_GENERIC_THEME_TOKENS = {"other", "misc", "miscellaneous", "various", "one-off", "one-offs"}


def _is_generic_theme(name: str) -> bool:
    norm = name.lower().strip()
    if norm in _GENERIC_THEME_TOKENS:
        return True
    return any(tok in norm.split() for tok in _GENERIC_THEME_TOKENS)


async def replace_project_themes(
    db: AsyncSession,
    project_name: str,
    tenant_id: str,
    tasks: list[_LoadedTask],
    extracted: ThemeExtractionResult,
) -> int:
    """Idempotently replace themes for a project. Returns the number of themes stored.

    Deletes existing Theme + ThemeTask rows for the project, then inserts the
    new extraction. Aggregates per-theme token totals and date ranges from the
    member task rows.
    """
    by_seq = {t.seq_id: t for t in tasks}

    # Delete existing themes for this project (cascade ThemeTask via FK is not
    # set up — delete junction rows explicitly first to avoid orphans).
    existing_ids_r = await db.execute(
        select(Theme.id)
        .where(Theme.project_name == project_name)
        .where(Theme.tenant_id == tenant_id)
    )
    existing_theme_ids = [row[0] for row in existing_ids_r.all()]
    if existing_theme_ids:
        from sqlalchemy import delete

        await db.execute(delete(ThemeTask).where(ThemeTask.theme_id.in_(existing_theme_ids)))
        await db.execute(delete(Theme).where(Theme.id.in_(existing_theme_ids)))
        await db.flush()

    stored = 0
    for theme in extracted.themes:
        members = [by_seq[tid] for tid in theme.task_ids if tid in by_seq]
        if not members:
            continue
        total_tokens = sum(m.prompt_tokens + m.completion_tokens for m in members)
        dates = [m.start_time for m in members if m.start_time is not None]
        first_date = min(dates) if dates else None
        last_date = max(dates) if dates else None

        row = Theme(
            tenant_id=tenant_id,
            project_name=project_name,
            name=theme.name,
            summary=theme.summary,
            total_tokens=total_tokens,
            task_count=len(members),
            first_date=first_date,
            last_date=last_date,
        )
        db.add(row)
        await db.flush()  # populate row.id

        for m in members:
            db.add(ThemeTask(theme_id=row.id, task_id=m.db_id, tenant_id=tenant_id))
        stored += 1

    await db.commit()
    return stored
