"""Shared JSONL parsing utilities for Claude Code transcript format.

Used by both entireio/parser.py and local/parsers/claude_code.py.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime

# Line types to skip when parsing Claude Code JSONL
SKIP_TYPES = {"progress", "system", "file-history-snapshot", "queue-operation", "summary"}

# Regex helpers for noise + signal extraction
_RE_COMMAND_NAME = re.compile(r"<command-name>([^<]+)</command-name>", re.IGNORECASE)
_RE_COMMAND_MESSAGE = re.compile(r"<command-message>([^<]+)</command-message>", re.IGNORECASE)
_RE_SKILL_DIR = re.compile(r"base directory for this skill:\s*(\S+)", re.IGNORECASE)


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
    """Check if a user line is a meta/system message that shouldn't create a turn.

    Covers Claude Code's own system markers and slash-command wrappers that
    don't represent real developer intent. Signals from these lines (which
    slash commands were used, which skills loaded, interrupt counts) should
    be extracted via ``extract_session_signals`` BEFORE filtering.
    """
    text = extract_user_content(msg).strip()
    if not text:
        return True
    head = text[:200]
    if head.startswith("[Request interrupted by user"):
        return True
    if head.startswith("<task-notification>"):
        return True
    if head.startswith("<local-command-caveat>") or head.startswith("<local-command-stdout>"):
        return True
    if "being continued from a previous conversation" in head:
        return True
    if head.lower().startswith("base directory for this skill:"):
        return True
    # Slash-command wrapper: drop only when the text is just a wrapper with no
    # substantive body. /compact specifically is always meta.
    if head.startswith("<command-name>/compact"):
        return True
    if head.startswith("<command-name>") or head.startswith("<command-message>"):
        # Strip all wrapper tags and see if anything substantive remains.
        stripped = _RE_COMMAND_NAME.sub("", text)
        stripped = _RE_COMMAND_MESSAGE.sub("", stripped)
        # Also drop common companion tags that ride along with slash commands.
        stripped = re.sub(r"<command-args>[^<]*</command-args>", "", stripped)
        stripped = stripped.strip()
        if not stripped or len(stripped) < 30:
            return True
    return False


def extract_session_signals(lines: list[dict]) -> dict:
    """Pull structured signals from raw JSONL lines BEFORE noise filtering.

    Returns a dict with:
      slash_commands: [{"name": str, "count": int}]  — sorted by count desc
      skills_used:    [{"path": str, "count": int}]  — sorted by count desc
      interrupts:     {"total": int, "during_tool_use": int}

    These get stashed on metadata_json for downstream consumption (UI badges,
    digest aggregates, friction analysis).
    """
    slash_counts: Counter[str] = Counter()
    skill_counts: Counter[str] = Counter()
    interrupts_total = 0
    interrupts_during_tool = 0

    for line in lines:
        if line.get("type") != "user":
            continue
        text = extract_user_content(line.get("message", {}))
        if not text:
            continue

        if text.startswith("[Request interrupted by user"):
            interrupts_total += 1
            if "for tool use" in text[:60]:
                interrupts_during_tool += 1
            continue

        for match in _RE_COMMAND_NAME.finditer(text):
            name = match.group(1).strip().lstrip("/")
            if name and name != "compact":  # /compact is housekeeping, not user intent
                slash_counts[name] += 1
        for match in _RE_COMMAND_MESSAGE.finditer(text):
            name = match.group(1).strip()
            if name:
                slash_counts[name] += 1

        for match in _RE_SKILL_DIR.finditer(text):
            path = match.group(1).strip().rstrip("/")
            if path:
                # Keep just the tail (e.g., ".claude/skills/github-pr-review")
                # so we don't leak per-user paths into shared data.
                short = path.split("/.claude/", 1)[-1] if "/.claude/" in path else path
                skill_counts[short] += 1

    return {
        "slash_commands": [{"name": n, "count": c} for n, c in slash_counts.most_common()],
        "skills_used": [{"path": p, "count": c} for p, c in skill_counts.most_common()],
        "interrupts": {"total": interrupts_total, "during_tool_use": interrupts_during_tool},
    }


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
