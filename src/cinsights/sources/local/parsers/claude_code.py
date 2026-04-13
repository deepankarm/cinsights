"""Parse Claude Code JSONL sessions into cinsights SpanData.

Uses shared parsing utilities from jsonl_utils (same format as entireio).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from cinsights.sources.base import SpanData, TraceData
from cinsights.sources.jsonl_utils import (
    extract_user_content,
    group_into_turns,
    parse_dt,
    parse_lines,
)

logger = logging.getLogger(__name__)


def parse_claude_code(
    data: bytes,
    trace_id: str,
    user_id: str | None = None,
    project_name: str | None = None,
) -> tuple[TraceData, list[SpanData]]:
    """Parse a Claude Code JSONL file into a span tree."""
    lines = parse_lines(data)
    if not lines:
        now = datetime.now(UTC)
        trace = TraceData(trace_id=trace_id, start_time=now, end_time=now)
        return trace, []

    turns = group_into_turns(lines)
    all_spans: list[SpanData] = []
    root_id = f"{trace_id}:root"

    # Extract model from first assistant message
    model_name = ""
    for line in lines:
        if line.get("type") == "assistant":
            m = line.get("message", {}).get("model")
            if m:
                model_name = m
                break

    # Session time boundaries
    all_timestamps = [parse_dt(line["timestamp"]) for line in lines if line.get("timestamp")]
    if all_timestamps:
        session_start = min(all_timestamps)
        session_end = max(all_timestamps)
    else:
        session_start = datetime.now(UTC)
        session_end = session_start

    for turn_num, turn in enumerate(turns, 1):
        turn_id = f"{trace_id}:turn:{turn_num}"
        user_line = turn.get("user")
        assistant_lines = turn.get("assistants", [])
        tool_results = turn.get("tool_results", {})

        turn_start = (
            parse_dt(user_line["timestamp"])
            if user_line and "timestamp" in user_line
            else session_start
        )
        turn_end = turn_start
        if assistant_lines:
            last_ts = assistant_lines[-1].get("timestamp")
            if last_ts:
                turn_end = parse_dt(last_ts)

        # Aggregate tokens (take max per message ID for streaming fragments)
        msg_tokens: dict[str, tuple[int, int]] = {}
        for aline in assistant_lines:
            msg = aline.get("message", {})
            msg_id = msg.get("id", "")
            usage = msg.get("usage", {})
            prompt_t = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            completion_t = usage.get("output_tokens", 0)
            key = msg_id or aline.get("uuid", "")
            existing = msg_tokens.get(key, (0, 0))
            msg_tokens[key] = (max(existing[0], prompt_t), max(existing[1], completion_t))

            m = msg.get("model")
            if m:
                model_name = m

        total_prompt = sum(p for p, _ in msg_tokens.values())
        total_completion = sum(c for _, c in msg_tokens.values())

        user_query = ""
        if user_line:
            user_query = extract_user_content(user_line.get("message", {}))

        turn_span = SpanData(
            span_id=turn_id,
            trace_id=trace_id,
            parent_id=root_id,
            name=f"Turn {turn_num}",
            span_kind="CHAIN",
            status_code="OK",
            start_time=turn_start,
            end_time=turn_end,
            attributes={
                "input.value": user_query[:2000] if user_query else "",
                "llm.token_count.prompt": total_prompt,
                "llm.token_count.completion": total_completion,
                "llm.model_name": model_name,
            },
        )
        all_spans.append(turn_span)

        # Tool spans
        for aline in assistant_lines:
            msg = aline.get("message", {})
            content_blocks = msg.get("content", [])
            if not isinstance(content_blocks, list):
                continue
            aline_ts = aline.get("timestamp")
            tool_start = parse_dt(aline_ts) if aline_ts else turn_start

            for block in content_blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue

                tool_use_id = block.get("id", "")
                tool_name = block.get("name", "unknown")
                tool_input = block.get("input", {})

                result_block = tool_results.get(tool_use_id, {})
                tool_output = result_block.get("content", "")
                is_error = result_block.get("is_error", False)

                tool_end = tool_start
                result_ts = turn.get("tool_result_timestamps", {}).get(tool_use_id)
                if result_ts:
                    tool_end = parse_dt(result_ts)

                input_str = (
                    json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)
                )

                tool_span = SpanData(
                    span_id=f"{trace_id}:tool:{tool_use_id}",
                    trace_id=trace_id,
                    parent_id=turn_id,
                    name=tool_name,
                    span_kind="CHAIN",
                    status_code="ERROR" if is_error else "OK",
                    start_time=tool_start,
                    end_time=tool_end,
                    attributes={
                        "tool.name": tool_name,
                        "tool.description": (
                            tool_input.get("description", "")
                            if isinstance(tool_input, dict)
                            else ""
                        ),
                        "input.value": input_str[:2000],
                        "output.value": (str(tool_output)[:2000] if tool_output else ""),
                    },
                )
                all_spans.append(tool_span)

    # Root span
    root_span = SpanData(
        span_id=root_id,
        trace_id=trace_id,
        parent_id=None,
        name="Session",
        span_kind="CHAIN",
        status_code="OK",
        start_time=session_start,
        end_time=session_end,
        attributes={
            "user.id": user_id or "",
            "llm.model_name": model_name,
            "session.id": trace_id,
            "project.name": project_name or "",
        },
    )
    all_spans.insert(0, root_span)

    trace = TraceData(
        trace_id=trace_id,
        start_time=session_start,
        end_time=session_end,
        spans=all_spans,
    )
    return trace, all_spans
