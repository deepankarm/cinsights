"""Shared JSONL parsing utilities for Claude Code transcript format.

Used by both entireio/parser.py and local/parsers/claude_code.py.
"""

from __future__ import annotations

import json
from datetime import datetime

# Line types to skip when parsing Claude Code JSONL
SKIP_TYPES = {"progress", "system", "file-history-snapshot", "queue-operation", "summary"}


def parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def extract_user_content(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    return str(content)


def extract_tool_results(message: dict) -> dict[str, dict]:
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


def parse_lines(data: bytes) -> list[dict]:
    """Parse JSONL bytes into a list of dicts, skipping non-conversation lines."""
    # Ensure we can decode as UTF-8; replace errors for robustness
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace").encode("utf-8")
    lines = []
    for raw_line in data.split(b"\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        line_type = obj.get("type", "")
        if line_type in SKIP_TYPES:
            continue
        if "snapshot" in obj and "messageId" in obj:
            continue
        lines.append(obj)
    return lines


def _is_image_source_line(msg: dict) -> bool:
    """Check if a user line is an image-source reference (not a real user message)."""
    text = extract_user_content(msg)
    return text.startswith("[Image source:") or text.startswith("[Image: source:")


def _is_meta_message(msg: dict) -> bool:
    """Check if a user line is a meta/system message that shouldn't create a turn."""
    text = extract_user_content(msg)
    return (
        text.startswith("<command-name>/compact")
        or text.startswith("<local-command-caveat>")
        or text.startswith("<local-command-stdout>")
        or "being continued from a previous conversation" in text[:200]
    )


def group_into_turns(lines: list[dict]) -> list[dict]:
    """Group conversation lines into turns (user -> assistant exchanges).

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
            tool_results = extract_tool_results(msg)

            if tool_results and current_turn:
                current_turn["tool_results"].update(tool_results)
                ts = line.get("timestamp", "")
                for tid in tool_results:
                    current_turn["tool_result_timestamps"][tid] = ts
            elif _is_image_source_line(msg) and current_turn:
                # Image source lines follow the [Image #N] text — merge, don't split
                pass
            elif _is_meta_message(msg):
                # /compact, local-command, continuation summaries aren't real turns
                pass
            else:
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
