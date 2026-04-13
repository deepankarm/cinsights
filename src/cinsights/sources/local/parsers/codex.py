"""Parse OpenAI Codex JSONL sessions into cinsights SpanData."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from cinsights.sources.base import SpanData, TraceData
from cinsights.sources.jsonl_utils import parse_dt

logger = logging.getLogger(__name__)


def parse_codex(
    data: bytes,
    trace_id: str,
    user_id: str | None = None,
    project_name: str | None = None,
) -> tuple[TraceData, list[SpanData]]:
    """Parse a Codex JSONL file into a span tree."""
    lines = _parse_jsonl(data)
    if not lines:
        now = datetime.now(UTC)
        trace = TraceData(trace_id=trace_id, start_time=now, end_time=now)
        return trace, []

    # Extract session metadata
    model_name = ""
    cwd = ""
    for line in lines:
        if line.get("type") == "session_meta":
            payload = line.get("payload", {})
            cwd = payload.get("cwd", "")
            break

    if not project_name and cwd:
        project_name = cwd.rstrip("/").rsplit("/", 1)[-1]

    # Group into turns based on user messages and task boundaries
    turns = _group_into_turns(lines)

    all_spans: list[SpanData] = []
    root_id = f"{trace_id}:root"

    all_timestamps = [parse_dt(line["timestamp"]) for line in lines if line.get("timestamp")]
    if all_timestamps:
        session_start = min(all_timestamps)
        session_end = max(all_timestamps)
    else:
        session_start = datetime.now(UTC)
        session_end = session_start

    for turn_num, turn in enumerate(turns, 1):
        turn_id = f"{trace_id}:turn:{turn_num}"

        turn_start = parse_dt(turn["start_ts"]) if turn.get("start_ts") else session_start
        turn_end = parse_dt(turn["end_ts"]) if turn.get("end_ts") else turn_start

        # Aggregate tokens from token_count events in this turn
        total_prompt = turn.get("input_tokens", 0)
        total_completion = turn.get("output_tokens", 0)

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
                "input.value": turn.get("user_query", "")[:2000],
                "llm.token_count.prompt": total_prompt,
                "llm.token_count.completion": total_completion,
                "llm.model_name": model_name,
            },
        )
        all_spans.append(turn_span)

        # Tool spans from function_call / function_call_output pairs
        for tool in turn.get("tools", []):
            tool_start = parse_dt(tool["start_ts"]) if tool.get("start_ts") else turn_start
            tool_end = parse_dt(tool["end_ts"]) if tool.get("end_ts") else tool_start

            tool_span = SpanData(
                span_id=f"{trace_id}:tool:{tool['call_id']}",
                trace_id=trace_id,
                parent_id=turn_id,
                name=tool["name"],
                span_kind="CHAIN",
                status_code="OK",
                start_time=tool_start,
                end_time=tool_end,
                attributes={
                    "tool.name": tool["name"],
                    "input.value": tool.get("input", "")[:2000],
                    "output.value": tool.get("output", "")[:2000],
                },
            )
            all_spans.append(tool_span)

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


def _parse_jsonl(data: bytes) -> list[dict]:
    lines = []
    for raw_line in data.split(b"\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            lines.append(json.loads(raw_line))
        except json.JSONDecodeError:
            continue
    return lines


def _group_into_turns(lines: list[dict]) -> list[dict]:
    """Group Codex JSONL lines into turns.

    A turn starts with a user message (response_item with role=user and actual
    user content) and ends at the next user message or end of file.
    """
    turns: list[dict] = []
    current_turn: dict | None = None

    # Track pending function calls for pairing with outputs
    pending_calls: dict[str, dict] = {}

    for line in lines:
        line_type = line.get("type", "")
        payload = line.get("payload", {})
        ts = line.get("timestamp", "")

        if line_type == "response_item" and payload.get("role") == "user":
            # Check if this has actual user content (not just system/context)
            content = payload.get("content", [])
            user_text = ""
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "input_text":
                    text = block.get("text", "")
                    # Skip system context injections
                    if not text.startswith("<") and not text.startswith("#"):
                        user_text = text
                        break

            if user_text:
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    "user_query": user_text,
                    "start_ts": ts,
                    "end_ts": ts,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "tools": [],
                }

        elif line_type == "event_msg":
            evt_type = payload.get("type", "")
            if evt_type == "user_message" and not current_turn:
                current_turn = {
                    "user_query": payload.get("message", ""),
                    "start_ts": ts,
                    "end_ts": ts,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "tools": [],
                }
            elif evt_type == "token_count" and current_turn:
                current_turn["input_tokens"] += payload.get("input_tokens", 0)
                current_turn["output_tokens"] += payload.get("output_tokens", 0)

            if current_turn and ts:
                current_turn["end_ts"] = ts

        elif line_type == "response_item" and payload.get("type") == "function_call":
            call_id = payload.get("call_id", "")
            name = payload.get("name", "unknown")
            arguments = payload.get("arguments", "")
            pending_calls[call_id] = {
                "call_id": call_id,
                "name": name,
                "input": arguments[:2000],
                "output": "",
                "start_ts": ts,
                "end_ts": ts,
            }
            if current_turn and ts:
                current_turn["end_ts"] = ts

        elif line_type == "response_item" and payload.get("type") == "function_call_output":
            call_id = payload.get("call_id", "")
            output = payload.get("output", "")
            if call_id in pending_calls:
                pending_calls[call_id]["output"] = str(output)[:2000]
                pending_calls[call_id]["end_ts"] = ts
                if current_turn:
                    current_turn["tools"].append(pending_calls.pop(call_id))
                    current_turn["end_ts"] = ts

        elif current_turn and ts:
            current_turn["end_ts"] = ts

    # Flush remaining pending calls
    if current_turn:
        for call in pending_calls.values():
            current_turn["tools"].append(call)
        turns.append(current_turn)

    return turns
