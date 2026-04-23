"""Tier 0 quality metrics computed from session data without LLM.

Each metric is a standalone function for testability and extensibility.
All take ToolCall rows and/or context growth data, return a value or None.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinsights.db.models import ToolCall

# Tool classification
_READ_TOOLS = {"Read", "Glob", "Grep", "Search", "ListDir", "WebFetch", "WebSearch"}
_EDIT_TOOLS = {"Edit", "NotebookEdit"}
_WRITE_TOOLS = {"Write"}
_MUTATION_TOOLS = _EDIT_TOOLS | _WRITE_TOOLS
_SUBAGENT_TOOLS = {"Agent", "Task"}


def compute_all(
    tool_calls: list[ToolCall],
    context_growth: list[dict] | None = None,
    total_tokens: int = 0,
) -> dict:
    """Compute all Tier 0 quality metrics for a session.

    Returns a dict of metric_name → value, ready to set on CodingSession.
    """
    turn_count = len(context_growth) if context_growth else None
    tc_count = len(tool_calls)

    return {
        "read_edit_ratio": read_edit_ratio(tool_calls),
        "edits_without_read_pct": edits_without_read_pct(tool_calls),
        "research_mutation_ratio": research_mutation_ratio(tool_calls),
        "write_vs_edit_pct": write_vs_edit_pct(tool_calls),
        "error_rate": error_rate(tool_calls),
        "repeated_edits_count": repeated_edits_to_same_file(tool_calls),
        "subagent_spawn_rate": subagent_spawn_rate(tool_calls),
        "tokens_per_useful_edit": tokens_per_useful_edit(tool_calls, total_tokens),
        "context_pressure_score": context_pressure(context_growth),
        "turn_count": turn_count,
        "tool_calls_per_turn": (
            round(tc_count / turn_count, 1) if turn_count and tc_count else None
        ),
        "error_retry_sequences": error_retry_sequences(tool_calls),
        "context_resets": context_resets(context_growth),
        "duplicate_read_count": duplicate_read_count(tool_calls),
    }


def read_edit_ratio(tool_calls: list[ToolCall]) -> float | None:
    """Ratio of Read operations to Edit operations.

    Higher = agent researches before modifying. Good: ~6.6, Degraded: ~2.0
    """
    reads = sum(1 for tc in tool_calls if tc.tool_name in _READ_TOOLS)
    edits = sum(1 for tc in tool_calls if tc.tool_name in _EDIT_TOOLS)
    if edits == 0:
        return None
    return round(reads / edits, 2)


def edits_without_read_pct(tool_calls: list[ToolCall]) -> float | None:
    """Percentage of Edit calls where the file was not Read first.

    Lower = better. Good: ~6%, Degraded: ~34%
    """
    edits = [tc for tc in tool_calls if tc.tool_name in _EDIT_TOOLS]
    if not edits:
        return None

    read_files: set[str] = set()
    blind_edits = 0

    for tc in tool_calls:
        file_path = _extract_file_path(tc.input_value)
        if not file_path:
            continue
        if tc.tool_name in _READ_TOOLS:
            read_files.add(file_path)
        elif tc.tool_name in _EDIT_TOOLS and file_path not in read_files:
            blind_edits += 1

    return round(blind_edits / len(edits) * 100, 1)


def research_mutation_ratio(tool_calls: list[ToolCall]) -> float | None:
    """Ratio of research (Read+Grep+Glob) to mutation (Edit+Write).

    Good: ~8.7, Degraded: ~2.8
    """
    research = sum(1 for tc in tool_calls if tc.tool_name in _READ_TOOLS)
    mutations = sum(1 for tc in tool_calls if tc.tool_name in _MUTATION_TOOLS)
    if mutations == 0:
        return None
    return round(research / mutations, 2)


def write_vs_edit_pct(tool_calls: list[ToolCall]) -> float | None:
    """Write (full-file) calls as percentage of all mutations.

    Good: ~5%, Degraded: ~11%
    """
    writes = sum(1 for tc in tool_calls if tc.tool_name in _WRITE_TOOLS)
    mutations = sum(1 for tc in tool_calls if tc.tool_name in _MUTATION_TOOLS)
    if mutations == 0:
        return None
    return round(writes / mutations * 100, 1)


def error_rate(tool_calls: list[ToolCall]) -> float | None:
    """Percentage of tool calls that failed."""
    if not tool_calls:
        return None
    failed = sum(1 for tc in tool_calls if not tc.success)
    return round(failed / len(tool_calls) * 100, 1)


def repeated_edits_to_same_file(tool_calls: list[ToolCall]) -> int:
    """Count of consecutive Edit calls to the same file (thrashing)."""
    count = 0
    last_edit_file = None
    for tc in tool_calls:
        if tc.tool_name in _EDIT_TOOLS:
            file_path = _extract_file_path(tc.input_value)
            if file_path and file_path == last_edit_file:
                count += 1
            last_edit_file = file_path
        else:
            last_edit_file = None
    return count


def subagent_spawn_rate(tool_calls: list[ToolCall]) -> float | None:
    """Agent/Task tool calls as percentage of total tool calls."""
    if not tool_calls:
        return None
    spawns = sum(1 for tc in tool_calls if tc.tool_name in _SUBAGENT_TOOLS)
    return round(spawns / len(tool_calls) * 100, 1)


def tokens_per_useful_edit(tool_calls: list[ToolCall], total_tokens: int) -> float | None:
    """Tokens consumed per successful Edit+Write call.

    Lower = more efficient. Measures cost of productive output.
    """
    useful = sum(1 for tc in tool_calls if tc.tool_name in _MUTATION_TOOLS and tc.success)
    if useful == 0 or total_tokens == 0:
        return None
    return round(total_tokens / useful, 0)


def context_pressure(context_growth: list[dict] | None) -> float | None:
    """Score 0-1 measuring how fast prompt tokens grow across turns.

    High score = context is growing steeply, approaching limits.
    Computed as the fraction of turns where prompt_tokens increased
    by more than 50% over the previous turn.
    """
    if not context_growth or len(context_growth) < 3:
        return None

    steep_increases = 0
    comparisons = 0
    for i in range(1, len(context_growth)):
        prev = context_growth[i - 1].get("prompt_tokens", 0)
        curr = context_growth[i].get("prompt_tokens", 0)
        if prev > 0:
            comparisons += 1
            if curr > prev * 1.5:
                steep_increases += 1

    if comparisons == 0:
        return None
    return round(steep_increases / comparisons, 2)


def error_retry_sequences(tool_calls: list[ToolCall]) -> int:
    """Count error→retry patterns: a failed tool call followed by the same tool.

    Indicates the agent retried an approach without changing strategy.
    """
    count = 0
    for i in range(len(tool_calls) - 1):
        if not tool_calls[i].success:
            # Check next few calls (within 3) for same tool name
            for j in range(i + 1, min(i + 4, len(tool_calls))):
                if tool_calls[j].tool_name == tool_calls[i].tool_name:
                    count += 1
                    break
    return count


def context_resets(context_growth: list[dict] | None) -> int:
    """Count turns where prompt_tokens dropped significantly (>40%).

    A large drop indicates compaction or context reset — the agent had to
    re-read context, wasting tokens on content it already processed.
    """
    if not context_growth or len(context_growth) < 2:
        return 0

    count = 0
    for i in range(1, len(context_growth)):
        prev = context_growth[i - 1].get("prompt_tokens", 0)
        curr = context_growth[i].get("prompt_tokens", 0)
        if prev > 1000 and curr < prev * 0.6:
            count += 1
    return count


def duplicate_read_count(tool_calls: list[ToolCall]) -> int:
    """Count Read tool calls on files that were already read earlier.

    Re-reading the same file wastes tokens on content already in context.
    """
    read_files: dict[str, int] = {}  # file_path → count
    duplicates = 0
    for tc in tool_calls:
        if tc.tool_name not in _READ_TOOLS:
            continue
        file_path = _extract_file_path(tc.input_value)
        if not file_path:
            continue
        if file_path in read_files:
            duplicates += 1
        read_files[file_path] = read_files.get(file_path, 0) + 1
    return duplicates


def _extract_file_path(input_value: str | None) -> str | None:
    """Extract file_path from tool input JSON or plain text."""
    if not input_value:
        return None
    if '"file_path"' in input_value:
        try:
            data = json.loads(input_value)
            if isinstance(data, dict):
                return data.get("file_path")
        except (json.JSONDecodeError, TypeError):
            pass
    for part in input_value.split():
        if "/" in part and not part.startswith("http"):
            return part.strip('"').strip("'")
    return None
