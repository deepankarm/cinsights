"""Tier 0 quality metrics computed from session data without LLM.

Each metric is a standalone function for testability and extensibility.
All take ToolCall rows and/or context growth data, return a float or None.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinsights.db.models import ToolCall

# Tool classification
_READ_TOOLS = {"Read", "Glob", "Grep", "Search", "ListDir", "WebFetch", "WebSearch"}
_EDIT_TOOLS = {"Edit", "NotebookEdit"}
_WRITE_TOOLS = {"Write"}
_MUTATION_TOOLS = _EDIT_TOOLS | _WRITE_TOOLS

# Reasoning loop patterns in assistant text
_LOOP_PATTERNS = re.compile(
    r"\b(?:oh wait|actually,|let me reconsider|hmm,? actually|no wait|"
    r"I was wrong|let me re-read|I made an error|that's not right|"
    r"wait,? that|I need to rethink|I misunderstood)\b",
    re.IGNORECASE,
)

# Premature stopping / ownership dodging phrases
_STOP_PHRASES = re.compile(
    r"\b(?:you (?:can|could|should|might|may) (?:try|do|handle|finish|complete|adjust)|"
    r"I'll leave (?:it|that|this) to you|"
    r"beyond (?:my|the) scope|"
    r"I can't (?:determine|know|tell)|"
    r"you'll need to (?:manually|decide)|"
    r"simplest (?:fix|approach|solution|change))\b",
    re.IGNORECASE,
)


def compute_all(
    tool_calls: list[ToolCall],
    context_growth: list[dict] | None = None,
) -> dict[str, float | None]:
    """Compute all quality metrics for a session.

    Returns a dict of metric_name → value, ready to set on CodingSession.
    """
    return {
        "read_edit_ratio": read_edit_ratio(tool_calls),
        "edits_without_read_pct": edits_without_read_pct(tool_calls),
        "user_interrupts_per_1k": None,  # requires turn-level data, computed separately
        "research_mutation_ratio": research_mutation_ratio(tool_calls),
        "write_vs_edit_pct": write_vs_edit_pct(tool_calls),
        "reasoning_loops_per_1k": reasoning_loops_per_1k(tool_calls),
        "error_rate": error_rate(tool_calls),
    }


def read_edit_ratio(tool_calls: list[ToolCall]) -> float | None:
    """Ratio of Read operations to Edit operations.

    Higher is better — agent researches before modifying.
    Good: ~6.6, Degraded: ~2.0
    """
    reads = sum(1 for tc in tool_calls if tc.tool_name in _READ_TOOLS)
    edits = sum(1 for tc in tool_calls if tc.tool_name in _EDIT_TOOLS)
    if edits == 0:
        return None
    return round(reads / edits, 2)


def edits_without_read_pct(tool_calls: list[ToolCall]) -> float | None:
    """Percentage of Edit calls where the file was not Read recently.

    Lower is better — agent should read before editing.
    Good: ~6%, Degraded: ~34%
    """
    edits = [tc for tc in tool_calls if tc.tool_name in _EDIT_TOOLS]
    if not edits:
        return None

    # Track which files have been read (by file path from input_value)
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

    total_edits = len(edits)
    if total_edits == 0:
        return None
    return round(blind_edits / total_edits * 100, 1)


def research_mutation_ratio(tool_calls: list[ToolCall]) -> float | None:
    """Ratio of research (Read+Grep+Glob) to mutation (Edit+Write).

    Broader version of read_edit_ratio.
    Good: ~8.7, Degraded: ~2.8
    """
    research = sum(1 for tc in tool_calls if tc.tool_name in _READ_TOOLS)
    mutations = sum(1 for tc in tool_calls if tc.tool_name in _MUTATION_TOOLS)
    if mutations == 0:
        return None
    return round(research / mutations, 2)


def write_vs_edit_pct(tool_calls: list[ToolCall]) -> float | None:
    """Write (full-file) calls as percentage of all mutations.

    Higher means more full-file rewrites vs surgical edits.
    Good: ~5%, Degraded: ~11%
    """
    writes = sum(1 for tc in tool_calls if tc.tool_name in _WRITE_TOOLS)
    mutations = sum(1 for tc in tool_calls if tc.tool_name in _MUTATION_TOOLS)
    if mutations == 0:
        return None
    return round(writes / mutations * 100, 1)


def reasoning_loops_per_1k(tool_calls: list[ToolCall]) -> float | None:
    """Self-contradiction phrases per 1K tool calls.

    Detected from tool output text (assistant reasoning visible in tool I/O).
    Good: ~8, Degraded: ~27
    """
    if not tool_calls:
        return None

    loop_count = 0
    for tc in tool_calls:
        # Check output for reasoning loops (assistant text sometimes in output)
        if tc.output_value:
            loop_count += len(_LOOP_PATTERNS.findall(tc.output_value))
        # Also check input (some tools carry assistant reasoning)
        if tc.input_value:
            loop_count += len(_LOOP_PATTERNS.findall(tc.input_value))

    return round(loop_count / len(tool_calls) * 1000, 1)


def error_rate(tool_calls: list[ToolCall]) -> float | None:
    """Percentage of tool calls that failed."""
    if not tool_calls:
        return None
    failed = sum(1 for tc in tool_calls if not tc.success)
    return round(failed / len(tool_calls) * 100, 1)


def stop_phrase_count(tool_calls: list[ToolCall]) -> int:
    """Count of premature stopping / ownership dodging phrases."""
    count = 0
    for tc in tool_calls:
        if tc.output_value:
            count += len(_STOP_PHRASES.findall(tc.output_value))
    return count


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


def _extract_file_path(input_value: str | None) -> str | None:
    """Extract file_path from tool input JSON or plain text."""
    if not input_value:
        return None
    # Try JSON format: {"file_path": "..."}
    if '"file_path"' in input_value:
        import json

        try:
            data = json.loads(input_value)
            if isinstance(data, dict):
                return data.get("file_path")
        except (json.JSONDecodeError, TypeError):
            pass
    # Try to find a path-like string
    for part in input_value.split():
        if "/" in part and not part.startswith("http"):
            return part.strip('"').strip("'")
    return None
