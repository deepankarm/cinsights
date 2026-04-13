"""Parse Entire.co full.jsonl transcripts into cinsights SpanData."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from cinsights.sources.base import SpanData, TraceData
from cinsights.sources.entireio.models import CommittedMetadata

logger = logging.getLogger(__name__)

# Line types to skip
_SKIP_TYPES = {"progress", "system", "file-history-snapshot", "queue-operation"}


def _parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _extract_user_content(message: dict) -> str:
    """Extract text content from a user message."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    # Skip tool results in user content extraction
                    pass
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    return str(content)


def _extract_tool_results(message: dict) -> dict[str, dict]:
    """Extract tool_result blocks from a user message, keyed by tool_use_id."""
    content = message.get("content", [])
    if not isinstance(content, list):
        return {}
    results = {}
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tool_use_id = block.get("tool_use_id", "")
            if tool_use_id:
                results[tool_use_id] = block
    return results


def parse_full_jsonl(
    data: bytes,
    checkpoint_id: str,
    session_idx: int,
    metadata: CommittedMetadata,
    user_id: str | None = None,
) -> tuple[TraceData, list[SpanData]]:
    """Parse a full.jsonl transcript into a synthesized span tree.

    Returns (TraceData, all_spans) matching the structure the cinsights
    pipeline expects: root span → Turn spans → tool spans.
    """
    lines = _parse_lines(data)
    if not lines:
        now = datetime.now(UTC)
        trace_id = f"entireio:{checkpoint_id}:{session_idx}"
        trace = TraceData(trace_id=trace_id, start_time=now, end_time=now)
        return trace, []

    trace_id = f"entireio:{checkpoint_id}:{session_idx}"
    turns = _group_into_turns(lines)

    all_spans: list[SpanData] = []
    root_id = f"{trace_id}:root"

    # Compute session boundaries from ALL line timestamps
    fallback_ts = metadata.created_at.isoformat()
    all_timestamps = [
        _parse_dt(line.get("timestamp", fallback_ts))
        for line in lines
        if line.get("timestamp")
    ]
    if all_timestamps:
        session_start = min(all_timestamps)
        session_end = max(all_timestamps)
    else:
        session_start = _parse_dt(fallback_ts)
        session_end = session_start

    # Build turn and tool spans
    for turn_num, turn in enumerate(turns, 1):
        turn_id = f"{trace_id}:turn:{turn_num}"
        user_line = turn.get("user")
        assistant_lines = turn.get("assistants", [])
        tool_results = turn.get("tool_results", {})

        # Turn timestamps
        turn_start = (
            _parse_dt(user_line["timestamp"])
            if user_line and "timestamp" in user_line
            else session_start
        )
        turn_end = turn_start
        if assistant_lines:
            last_ts = assistant_lines[-1].get("timestamp")
            if last_ts:
                turn_end = _parse_dt(last_ts)

        # Aggregate token counts from all assistant messages in this turn
        # (streaming fragments share the same message ID; take max per ID)
        msg_tokens: dict[str, tuple[int, int]] = {}
        model_name = metadata.model or ""
        for aline in assistant_lines:
            msg = aline.get("message", {})
            msg_id = msg.get("id", "")
            usage = msg.get("usage", {})
            # Full context = fresh input + cache creation + cache read
            prompt_t = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            completion_t = usage.get("output_tokens", 0)
            if msg_id:
                existing = msg_tokens.get(msg_id, (0, 0))
                # Take the max (last streaming fragment has final counts)
                msg_tokens[msg_id] = (
                    max(existing[0], prompt_t),
                    max(existing[1], completion_t),
                )
            else:
                msg_tokens[aline.get("uuid", "")] = (prompt_t, completion_t)

            m = msg.get("model")
            if m:
                model_name = m

        total_prompt = sum(p for p, _ in msg_tokens.values())
        total_completion = sum(c for _, c in msg_tokens.values())

        # User query
        user_query = ""
        if user_line:
            user_query = _extract_user_content(user_line.get("message", {}))

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

        # Extract tool spans from assistant content
        for aline in assistant_lines:
            msg = aline.get("message", {})
            content_blocks = msg.get("content", [])
            if not isinstance(content_blocks, list):
                continue
            aline_ts = aline.get("timestamp")
            tool_start = _parse_dt(aline_ts) if aline_ts else turn_start

            for block in content_blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue

                tool_use_id = block.get("id", "")
                tool_name = block.get("name", "unknown")
                tool_input = block.get("input", {})

                # Find matching tool_result
                result_block = tool_results.get(tool_use_id, {})
                tool_output = result_block.get("content", "")
                is_error = result_block.get("is_error", False)

                # Tool end time: from the tool_result's parent user message timestamp
                tool_end = tool_start
                result_ts = turn.get("tool_result_timestamps", {}).get(tool_use_id)
                if result_ts:
                    tool_end = _parse_dt(result_ts)

                # Format input for display
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
            "llm.model_name": metadata.model or "",
            "session.id": metadata.session_id,
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


def _parse_lines(data: bytes) -> list[dict]:
    """Parse JSONL bytes into a list of dicts, skipping non-conversation lines."""
    lines = []
    for raw_line in data.split(b"\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        line_type = obj.get("type", "")
        if line_type in _SKIP_TYPES:
            continue
        # Skip file-history-snapshot (also checked by key presence)
        if "snapshot" in obj and "messageId" in obj:
            continue
        lines.append(obj)
    return lines


def _group_into_turns(lines: list[dict]) -> list[dict]:
    """Group conversation lines into turns (user → assistant exchanges).

    Each turn is a dict with:
      - user: the user message line (or None for assistant-only turns)
      - assistants: list of assistant message lines
      - tool_results: {tool_use_id: tool_result_block} from user messages
      - tool_result_timestamps: {tool_use_id: timestamp} for timing
    """
    turns: list[dict] = []
    current_turn: dict | None = None

    for line in lines:
        line_type = line.get("type", "")

        if line_type == "user":
            msg = line.get("message", {})
            tool_results = _extract_tool_results(msg)

            if tool_results and current_turn:
                # This is a tool_result response, add to current turn
                current_turn["tool_results"].update(tool_results)
                ts = line.get("timestamp", "")
                for tid in tool_results:
                    current_turn["tool_result_timestamps"][tid] = ts
            else:
                # New turn starts with a user message
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    "user": line,
                    "assistants": [],
                    "tool_results": {},
                    "tool_result_timestamps": {},
                }

        elif line_type == "assistant":
            if current_turn is None:
                current_turn = {
                    "user": None,
                    "assistants": [],
                    "tool_results": {},
                    "tool_result_timestamps": {},
                }
            current_turn["assistants"].append(line)

    if current_turn:
        turns.append(current_turn)

    return turns
