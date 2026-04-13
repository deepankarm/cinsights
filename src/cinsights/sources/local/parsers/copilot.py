"""Parse GitHub Copilot CLI JSONL sessions into cinsights SpanData."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from cinsights.sources.base import SpanData, TraceData

logger = logging.getLogger(__name__)


def _parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def parse_copilot(
    data: bytes,
    trace_id: str,
    user_id: str | None = None,
    project_name: str | None = None,
) -> tuple[TraceData, list[SpanData]]:
    """Parse a Copilot CLI JSONL file into a span tree."""
    lines = _parse_jsonl(data)
    if not lines:
        now = datetime.now(UTC)
        trace = TraceData(trace_id=trace_id, start_time=now, end_time=now)
        return trace, []

    # Extract session metadata from session.start
    model_name = ""
    cwd = ""
    for line in lines:
        if line.get("type") == "session.start":
            ctx = line.get("data", {}).get("context", {})
            cwd = ctx.get("cwd", "")
            break

    if not project_name and cwd:
        project_name = cwd.rstrip("/").rsplit("/", 1)[-1]

    turns = _group_into_turns(lines)
    all_spans: list[SpanData] = []
    root_id = f"{trace_id}:root"

    all_timestamps = [_parse_dt(line["timestamp"]) for line in lines if line.get("timestamp")]
    if all_timestamps:
        session_start = min(all_timestamps)
        session_end = max(all_timestamps)
    else:
        session_start = datetime.now(UTC)
        session_end = session_start

    for turn_num, turn in enumerate(turns, 1):
        turn_id = f"{trace_id}:turn:{turn_num}"

        turn_start = _parse_dt(turn["start_ts"]) if turn.get("start_ts") else session_start
        turn_end = _parse_dt(turn["end_ts"]) if turn.get("end_ts") else turn_start

        total_prompt = turn.get("input_tokens", 0)
        total_completion = turn.get("output_tokens", 0)

        # Extract model from tool completions in this turn
        turn_model = turn.get("model", "") or model_name
        if turn_model:
            model_name = turn_model

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

        for tool in turn.get("tools", []):
            tool_start = _parse_dt(tool["start_ts"]) if tool.get("start_ts") else turn_start
            tool_end = _parse_dt(tool["end_ts"]) if tool.get("end_ts") else tool_start

            tool_span = SpanData(
                span_id=f"{trace_id}:tool:{tool['call_id']}",
                trace_id=trace_id,
                parent_id=turn_id,
                name=tool["name"],
                span_kind="CHAIN",
                status_code="ERROR" if not tool.get("success", True) else "OK",
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
    """Group Copilot JSONL lines into turns.

    A turn starts with a user.message and includes all subsequent assistant
    messages and tool calls until the next user.message.
    """
    turns: list[dict] = []
    current_turn: dict | None = None
    pending_tools: dict[str, dict] = {}  # toolCallId -> tool info

    for line in lines:
        line_type = line.get("type", "")
        data = line.get("data", {})
        ts = line.get("timestamp", "")

        if line_type == "user.message":
            if current_turn:
                # Flush pending tools
                for t in pending_tools.values():
                    current_turn["tools"].append(t)
                pending_tools.clear()
                turns.append(current_turn)

            content = data.get("content", "")
            current_turn = {
                "user_query": content,
                "start_ts": ts,
                "end_ts": ts,
                "input_tokens": 0,
                "output_tokens": 0,
                "tools": [],
                "model": "",
            }

        elif line_type == "assistant.message":
            if current_turn is None:
                current_turn = {
                    "user_query": "",
                    "start_ts": ts,
                    "end_ts": ts,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "tools": [],
                    "model": "",
                }

            output_tokens = data.get("outputTokens", 0)
            if output_tokens:
                current_turn["output_tokens"] += output_tokens

            # Extract tool requests from assistant messages
            for req in data.get("toolRequests", []):
                call_id = req.get("toolCallId", "")
                if call_id:
                    args = req.get("arguments", {})
                    input_str = json.dumps(args) if isinstance(args, dict) else str(args)
                    pending_tools[call_id] = {
                        "call_id": call_id,
                        "name": req.get("name", "unknown"),
                        "input": input_str[:2000],
                        "output": "",
                        "start_ts": ts,
                        "end_ts": ts,
                        "success": True,
                    }

            if ts:
                current_turn["end_ts"] = ts

        elif line_type == "tool.execution_complete":
            call_id = data.get("toolCallId", "")
            model = data.get("model", "")
            if model and current_turn:
                current_turn["model"] = model

            if call_id in pending_tools:
                result = data.get("result", {})
                pending_tools[call_id]["output"] = str(result.get("content", ""))[:2000]
                pending_tools[call_id]["end_ts"] = ts
                pending_tools[call_id]["success"] = data.get("success", True)
                if current_turn:
                    current_turn["tools"].append(pending_tools.pop(call_id))
                    current_turn["end_ts"] = ts

        elif current_turn and ts:
            current_turn["end_ts"] = ts

    if current_turn:
        for t in pending_tools.values():
            current_turn["tools"].append(t)
        turns.append(current_turn)

    return turns
