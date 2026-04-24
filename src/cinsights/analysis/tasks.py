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


# --- Prompts (proven in experiments) ---

SYSTEM_PROMPT = """\
You are analyzing a coding agent session transcript to identify distinct tasks.

A "task" is a coherent unit of work the developer pursued across consecutive turns.
Task boundaries occur when the developer:
- Explicitly switches to a new topic ("Now let's work on X", "Moving on to...")
- Starts working on unrelated files/features after completing something
- Resumes after a context continuation message
- Shifts from one area (e.g. backend) to a completely different one (e.g. UI)

Rules:
- Every turn must belong to exactly one task (no gaps, no overlaps)
- Tasks should be 2-30 turns typically (not 1 turn unless truly isolated)
- Iterative refinement on the same feature is ONE task, not many
- Name tasks concisely: "Add token tracking UI", "Refactor scenario API", etc.
- If a turn is just a quick follow-up to the previous topic, it's part of the same task
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
    """Compute per-task waste using the 'compact at task boundary' model.

    Returns a list of dicts with per-task metrics:
    - prompt_tokens_total, completion_tokens_total
    - context_at_start, estimated_waste_tokens
    """
    # Build turn → context_growth lookup
    growth_by_turn = {entry["turn"]: entry for entry in context_growth}

    results = []
    for i, task in enumerate(tasks):
        # Sum tokens across turns in this task
        prompt_total = 0
        completion_total = 0
        for turn_num in range(task.start_turn, task.end_turn + 1):
            entry = growth_by_turn.get(turn_num, {})
            prompt_total += entry.get("total_billed_prompt", 0) or entry.get("prompt_tokens", 0)
            completion_total += entry.get("completion_tokens", 0)

        # Context at task start = prompt_tokens at first turn
        first_entry = growth_by_turn.get(task.start_turn, {})
        context_at_start = first_entry.get("prompt_tokens", 0)

        # Waste: for first task, 0 (fresh session). For subsequent tasks,
        # estimate how much a /compact would save at this boundary.
        if i == 0:
            waste = 0
        else:
            saveable_per_turn = int(context_at_start * (1 - compact_ratio))
            waste = saveable_per_turn * task.turn_count

        results.append(
            {
                "prompt_tokens_total": prompt_total,
                "completion_tokens_total": completion_total,
                "context_at_start": context_at_start,
                "estimated_waste_tokens": waste,
            }
        )

    return results


# --- Analyzer ---


class TaskAnalyzer(LLMAnalyzer):
    """Detect task boundaries in coding sessions using LLM segmentation."""

    async def segment(
        self, trace: TraceData, spans: list[SpanData]
    ) -> TaskSegmentationResult | None:
        """Segment a session into tasks. Returns None for small sessions."""
        turn_summary, turn_count = build_turn_summary(spans)

        if turn_count < 3:
            logger.debug(
                "Skipping task segmentation for %s (only %d turns)", trace.trace_id, turn_count
            )
            return None

        user_prompt = USER_PROMPT_TEMPLATE.format(turn_count=turn_count, turns=turn_summary)

        logger.info(
            "Segmenting tasks for %s (%d turns, ~%d chars)",
            trace.trace_id,
            turn_count,
            len(user_prompt),
        )

        from cinsights.db.models import LLMCallKind, LLMCallScopeType

        result, _, _ = await self._run_llm(
            TaskSegmentationResult,
            SYSTEM_PROMPT,
            user_prompt,
            call_kind=LLMCallKind.TASK_SEGMENTATION,
            scope_type=LLMCallScopeType.SESSION,
            scope_id=trace.trace_id,
            max_tokens=4096,
        )

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
