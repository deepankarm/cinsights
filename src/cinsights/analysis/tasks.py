"""Task segmentation: detect coherent tasks within a coding session.

Uses an LLM to identify task boundaries from compressed per-turn summaries
(user prompt + tools + files). Each task gets a name, description, turn range,
and optional waste estimation based on compaction analysis.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter

from pydantic import BaseModel, Field

from cinsights.analysis import LLMAnalyzer
from cinsights.sources.base import SpanData, TraceData

logger = logging.getLogger(__name__)


# --- Pydantic models ---


class TaskItem(BaseModel):
    """A coherent unit of work spanning consecutive turns."""

    start_turn: int
    end_turn: int
    name: str = Field(description="3-8 word concise task name")
    description: str = Field(description="1-2 sentence description")
    turn_count: int


class TaskSegmentationResult(BaseModel):
    """LLM output: list of tasks covering the full session."""

    tasks: list[TaskItem]
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0


# --- Prompts (proven in experiments) ---

SYSTEM_PROMPT = """\
You are analyzing a coding agent session transcript to identify distinct tasks.

A "task" is a coherent unit of work the developer pursued across consecutive turns.
Task boundaries occur when the developer:
- Explicitly switches to a new topic ("Now let's work on X", "Moving on to...")
- Starts working on unrelated files/features after completing something
- Resumes after a context continuation message
- Shifts from one area (e.g. backend) to a completely different one (e.g. UI)
- Shifts between sub-features even within a larger feature (e.g. "build the API" → "build the UI for it")

Segmentation rules:
- Every turn must belong to exactly one task (no gaps, no overlaps)
- Tasks should be 3-25 turns typically. Avoid 1-2 turn tasks: a trailing
  "commit and push" or "run tests" turn belongs to the task it concludes,
  not its own task.
- Break large features into sub-tasks: "Add auth API endpoint", "Build auth UI form",
  "Write auth tests" — not just "Add auth"
- For long sessions (50+ turns), expect 5-15+ tasks — a single 50-turn task is too coarse

NAMING — this is the most important rule. Generic activity labels are useless.

Two requirements for every name:

1. The name must answer "what feature/file/bug is this about?", not "what
   activity is this?". Look across ALL turns in the task (not just the first
   user prompt) for the specific subject: file names, function names, test
   names, error names, features being built. Slash-command templates the user
   invoked (e.g. "Simplify: Code Review and Cleanup", "Implement plan") are
   NOT the subject — they tell you the activity, not the work product.

2. The most DISTINCTIVE word must come early in the name. Lead with the
   specific noun (feature, component, file, test). Burying it after generic
   verbs ("Code review and cleanup of search-related files") makes the name
   indistinguishable from other code-cleanup tasks. Rewrite to put the
   distinctive subject up front: "Search TUI cleanup and review".

Good names (illustrative — these are HYPOTHETICAL examples from unrelated
projects, NOT hints about the current session's content):
  - "User session timeout — fix race in renewal"
  - "Stripe webhook retry — add exponential backoff"
  - "Email queue worker — switch from sync to background"
  - "TestUserAuth_RefreshTokenExpiry — debug intermittent failure"
  - "OAuth callback URL parsing — fix encoding bug"
  - "Mobile push registration — add iOS support"
  - "Admin CSV export — add date filtering"
  - "Image upload pipeline — switch to presigned URLs"

Bad names (REJECT and rewrite — these patterns generalize):
  - "Code review and cleanup of changes" → name the subject area being reviewed
  - "Commit and push changes" → fold into prior task, or name what was committed
  - "Debug failing test" → "<test name> — debug"
  - "Create pull request" → "<feature name> — open PR"
  - "Implement plan" → "<plan subject> — implement"
  - "Address bug, env detection, and refactor file ops"
      → "File operations refactor + env-detection bug"
  - "Address rate limit bypass and notification changes"
      → "Rate-limit bypass fix + notification changes"

Pull the actual subject from THIS session's transcript — the file names,
test names, errors, features mentioned in the turns. The examples above
show the SHAPE only; do not copy their domain content.

If the only signal you have for a turn-range is a slash-command template and
no specific files/tests/topics, prefer folding it into the adjacent task rather
than emitting a generic-named standalone task.
"""

USER_PROMPT_TEMPLATE = """\
Here is a session with {turn_count} turns. Each line shows:
`T<num> HH:MM | <user prompt> || tools: <tool:count> || files: <files touched>`

Segment this into tasks. Return every turn covered, no gaps.

---
{turns}
"""


# --- Turn summary builder ---


def build_turn_summary(spans: list[SpanData]) -> tuple[str, int]:
    """Build a compressed per-turn summary from span data.

    Returns (summary_text, turn_count).
    """
    turns = sorted(
        [s for s in spans if s.name.startswith("Turn ")],
        key=lambda s: int(s.name.split()[1]),
    )
    tools = [s for s in spans if s.parent_id and s.attributes.get("tool.name")]

    lines = []
    for t in turns:
        num = int(t.name.split()[1])
        ts = t.start_time.strftime("%H:%M")
        user_q = (t.attributes.get("input.value") or "").strip()[:300].replace("\n", " ")

        turn_tools = [s for s in tools if s.parent_id == t.span_id]
        tool_counts = Counter(s.attributes.get("tool.name", "?") for s in turn_tools)
        errors = sum(1 for s in turn_tools if s.status_code == "ERROR")

        files: set[str] = set()
        for s in turn_tools:
            inp = s.attributes.get("input.value", "")
            for m in re.finditer(r'"file_path":\s*"([^"]+)"', inp):
                files.add(m.group(1).split("/")[-1])

        tool_str = (
            ", ".join(f"{name}:{cnt}" for name, cnt in tool_counts.most_common(4))
            if tool_counts
            else ""
        )
        files_str = ", ".join(sorted(files)[:5]) if files else ""
        err_str = f" ERR:{errors}" if errors else ""

        line = f"T{num} {ts} | {user_q}"
        if tool_str:
            line += f" || tools: {tool_str}{err_str}"
        if files_str:
            line += f" || files: {files_str}"

        lines.append(line)

    return "\n".join(lines), len(turns)


# --- Waste estimation ---


def compute_task_waste(
    tasks: list[TaskItem],
    context_growth: list[dict],
    compact_ratio: float,
) -> list[dict]:
    """Compute per-task token usage and total savings from hypothetical compactions.

    Simulates a counterfactual where /compact runs at every task boundary.
    The hypothetical context at each turn is tracked forward so that
    compaction at boundary N correctly reduces the starting point for
    boundary N+1.

    Total savings = sum(actual_prompt) - sum(hypothetical_prompt) across
    all turns in tasks 2+.

    Returns a list of dicts with per-task metrics:
    - prompt_tokens_total, completion_tokens_total
    - context_at_start, estimated_waste_tokens
    """
    # Build turn → context_growth lookup
    growth_by_turn = {entry["turn"]: entry for entry in context_growth}

    # First pass: collect actual context at start/end of each task
    task_actual = []
    for task in tasks:
        first_entry = growth_by_turn.get(task.start_turn, {})
        last_entry = growth_by_turn.get(task.end_turn, {})
        context_at_start = first_entry.get("prompt_tokens", 0)
        context_at_end = last_entry.get("prompt_tokens", 0)
        task_actual.append((context_at_start, context_at_end))

    # Second pass: simulate hypothetical context and compute waste
    hypothetical_context = task_actual[0][0] if task_actual else 0
    results = []
    for i, task in enumerate(tasks):
        # Sum billed tokens across turns in this task
        prompt_total = 0
        completion_total = 0
        for turn_num in range(task.start_turn, task.end_turn + 1):
            entry = growth_by_turn.get(turn_num, {})
            prompt_total += entry.get("total_billed_prompt", 0) or entry.get("prompt_tokens", 0)
            completion_total += entry.get("completion_tokens", 0)

        actual_start, actual_end = task_actual[i]
        growth = actual_end - actual_start

        if i > 0:
            # Compact at this boundary
            hypothetical_context *= compact_ratio

        # Per-turn saving is constant within a task (same growth rate)
        saving_per_turn = actual_start - hypothetical_context
        waste = max(0, int(saving_per_turn * task.turn_count))

        results.append(
            {
                "prompt_tokens_total": prompt_total,
                "completion_tokens_total": completion_total,
                "context_at_start": actual_start,
                "estimated_waste_tokens": waste,
            }
        )

        # Grow hypothetical by the same amount as actual during this task
        hypothetical_context += growth

    return results


# --- Analyzer ---


class TaskAnalyzer(LLMAnalyzer):
    """Detect task boundaries in coding sessions using LLM segmentation."""

    async def segment(
        self, trace: TraceData, spans: list[SpanData]
    ) -> TaskSegmentationResult | None:
        """Segment a session into tasks."""
        turn_summary, turn_count = build_turn_summary(spans)

        user_prompt = USER_PROMPT_TEMPLATE.format(turn_count=turn_count, turns=turn_summary)

        logger.info(
            "Segmenting tasks for %s (%d turns, ~%d chars)",
            trace.trace_id,
            turn_count,
            len(user_prompt),
        )

        from cinsights.db.models import LLMCallKind, LLMCallScopeType

        result, prompt_tokens, completion_tokens = await self._run_llm(
            TaskSegmentationResult,
            SYSTEM_PROMPT,
            user_prompt,
            call_kind=LLMCallKind.TASK_SEGMENTATION,
            scope_type=LLMCallScopeType.SESSION,
            scope_id=trace.trace_id,
            max_tokens=4096,
        )
        if result is not None:
            result.usage_prompt_tokens = prompt_tokens
            result.usage_completion_tokens = completion_tokens
        return result

    async def segment_batch(
        self,
        items: list[tuple[TraceData, list[SpanData]]],
        max_concurrency: int = 5,
    ) -> list[TaskSegmentationResult | None | BaseException]:
        """Segment multiple sessions concurrently.

        Returns a list matching input order. Successful runs return
        TaskSegmentationResult or None (skipped); failures return the exception.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(
            trace: TraceData, spans: list[SpanData]
        ) -> TaskSegmentationResult | None:
            async with semaphore:
                return await self.segment(trace, spans)

        tasks = [_bounded(trace, spans) for trace, spans in items]
        return list(await asyncio.gather(*tasks, return_exceptions=True))
