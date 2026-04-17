"""What each trace source emits, and what each metric needs.

Phoenix's plugin is blind to most behavioral signals; local/entireio JSONL
is not. Metrics declare their required capabilities here so the Doctor
surface can show which sources support them instead of rendering zeros.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    ASSISTANT_RESPONSE_TEXT = "assistant.response.text"
    USER_PROMPT_TEXT = "user.prompt.text"
    TOOL_INPUT = "tool.input"
    TOOL_OUTPUT = "tool.output"
    USER_INTERRUPT_MARKER = "user.interrupt.marker"
    PERMISSION_OUTCOME = "permission.outcome"
    TOKEN_CACHE_READ = "token.cache_read"
    TOKEN_CACHE_WRITE = "token.cache_write"
    TOKEN_THINKING = "token.thinking"
    THINKING_TEXT = "thinking.text"
    THINKING_SIGNATURE = "thinking.signature"
    HARNESS_AGENT_VERSION = "harness.agent_version"
    HARNESS_EFFORT_LEVEL = "harness.effort_level"
    HARNESS_CLAUDE_MD = "harness.claude_md"
    SUBAGENT_SIDECHAIN = "subagent.sidechain"


CAPABILITY_DESCRIPTIONS: dict[Capability, str] = {
    Capability.ASSISTANT_RESPONSE_TEXT: "Agent's natural-language response per turn.",
    Capability.USER_PROMPT_TEXT: "User's prompt text per turn.",
    Capability.TOOL_INPUT: "Arguments supplied to each tool invocation.",
    Capability.TOOL_OUTPUT: "Output / stderr returned by each tool invocation.",
    Capability.USER_INTERRUPT_MARKER: "User cancelled a turn mid-execution.",
    Capability.PERMISSION_OUTCOME: "Whether the user granted or denied a permission request.",
    Capability.TOKEN_CACHE_READ: "Prompt-cache read token count per LLM call.",
    Capability.TOKEN_CACHE_WRITE: "Prompt-cache write token count per LLM call.",
    Capability.TOKEN_THINKING: "Thinking-token count separate from completion.",
    Capability.THINKING_TEXT: "Raw thinking content when not redacted.",
    Capability.THINKING_SIGNATURE: "Thinking-block signature (reasoning-depth proxy).",
    Capability.HARNESS_AGENT_VERSION: "Agent client version.",
    Capability.HARNESS_EFFORT_LEVEL: "Effort setting per turn or session.",
    Capability.HARNESS_CLAUDE_MD: "CLAUDE.md / memory file presence and hash.",
    Capability.SUBAGENT_SIDECHAIN: "Session is a sidechain of a parent session.",
}


SOURCE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "local": frozenset(Capability),
    "entireio": frozenset(Capability) - {Capability.HARNESS_CLAUDE_MD},
    "phoenix": frozenset(
        {Capability.USER_PROMPT_TEXT, Capability.TOOL_INPUT, Capability.TOOL_OUTPUT}
    ),
}


METRIC_REQUIREMENTS: dict[str, frozenset[Capability]] = {
    "llm_call_log.cache_tokens": frozenset(
        {Capability.TOKEN_CACHE_READ, Capability.TOKEN_CACHE_WRITE}
    ),
    "llm_call_log.thinking_tokens": frozenset({Capability.TOKEN_THINKING}),
    "interrupt_count": frozenset({Capability.USER_INTERRUPT_MARKER}),
}


def all_known_sources() -> tuple[str, ...]:
    return tuple(SOURCE_CAPABILITIES.keys())


def capabilities_for_source(source: str) -> frozenset[Capability]:
    return SOURCE_CAPABILITIES.get(source, frozenset())


def missing_for_source(source: str) -> frozenset[Capability]:
    return frozenset(Capability) - capabilities_for_source(source)


def session_supports_metric(source: str, metric_id: str) -> bool:
    """Unknown metrics pass (no requirements registered yet). Unknown sources fail."""
    required = METRIC_REQUIREMENTS.get(metric_id)
    if required is None:
        return True
    if source not in SOURCE_CAPABILITIES:
        return False
    return required.issubset(SOURCE_CAPABILITIES[source])


def metrics_available_on(source: str) -> frozenset[str]:
    return frozenset(mid for mid in METRIC_REQUIREMENTS if session_supports_metric(source, mid))


def missing_capabilities_for_metric(source: str, metric_id: str) -> frozenset[Capability]:
    required = METRIC_REQUIREMENTS.get(metric_id, frozenset())
    return required - capabilities_for_source(source)
