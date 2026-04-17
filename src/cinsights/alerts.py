"""Detect dangerous operations in tool calls."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinsights.db.models import ToolCall

# (pattern, alert_kind) — first match wins per tool call
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brm\s+-(r|rf|fr)\b"), "destructive_rm"),
    (re.compile(r"\bgit\s+push\s+.*(-f|--force)\b"), "force_push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard_reset"),
    (re.compile(r"\b(cat|head|tail|less|more|Read)\b.*\.(env|pem|key)\b"), "credential_exposure"),
    (re.compile(r"\b(credentials\.json|id_rsa|id_ed25519|\.env)\b"), "credential_exposure"),
    (re.compile(r"\bcurl\b.*\|\s*(sh|bash)\b"), "pipe_to_shell"),
    (re.compile(r"\bwget\b.*\|\s*(sh|bash)\b"), "pipe_to_shell"),
    (re.compile(r"\bchmod\s+777\b"), "chmod_world_writable"),
    (re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.IGNORECASE), "sql_drop"),
]


def detect_alerts(tool_calls: list[ToolCall]) -> list[tuple[str, str, str | None]]:
    """Scan tool calls for dangerous ops.

    Returns list of (alert_kind, evidence, span_id).
    """
    results = []
    for tc in tool_calls:
        if tc.tool_name != "Bash" or not tc.input_value:
            continue
        # Extract command from JSON input
        try:
            cmd = json.loads(tc.input_value).get("command", "")
        except (json.JSONDecodeError, AttributeError):
            cmd = tc.input_value

        for pattern, kind in _PATTERNS:
            if pattern.search(cmd):
                results.append((kind, cmd[:500], tc.span_id))
                break  # one alert per tool call
    return results
