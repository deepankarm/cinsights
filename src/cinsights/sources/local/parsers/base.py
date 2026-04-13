from __future__ import annotations

import json
from enum import StrEnum


class AgentType(StrEnum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    COPILOT = "copilot"


def detect_agent(data: bytes) -> AgentType | None:
    """Detect agent type from the first few lines of a JSONL file."""
    for raw_line in data.split(b"\n")[:20]:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        line_type = obj.get("type", "")

        # Codex: has session_meta with codex originator
        if line_type == "session_meta":
            payload = obj.get("payload", {})
            originator = payload.get("originator", "")
            if originator.startswith("codex"):
                return AgentType.CODEX

        # Copilot: has session.start with producer
        if line_type == "session.start":
            data_field = obj.get("data", {})
            if data_field.get("producer") == "copilot-agent":
                return AgentType.COPILOT

        # Claude Code: has top-level "type": "user"/"assistant" with "sessionId"
        if line_type in ("user", "assistant") and "sessionId" in obj:
            return AgentType.CLAUDE_CODE

    return None
