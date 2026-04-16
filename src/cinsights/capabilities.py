"""Source capability vocabulary and per-metric requirement registry.

The problem this module solves: cinsights ingests from several sources
(``local`` JSONL, ``phoenix`` OTel, ``entireio`` git checkpoints) that are
**not uniformly rich**. Phoenix (via the current arize-claude-code-plugin)
does not, for example, emit the assistant's natural-language response text
— so BehavioralEvidence extraction has no substrate there. Silent
under-counting on Phoenix would be misleading; we want to **declare** what
each source can provide, then skip metrics whose requirements aren't met
and surface that fact honestly in the UI.

Concepts:

- :class:`Capability` — the vocabulary of spannable / session-level signals
  a source *might* expose. Add new members as new ticket work needs them;
  existing members never change name (it's a wire-format).
- ``SOURCE_CAPABILITIES`` — the honest, hand-curated map of what each of
  the three current sources actually emits today. When a source ships
  new instrumentation (or we file and land a Phoenix upstream fix per
  ``.local/phoenix-gaps.md``), update this map.
- ``METRIC_REQUIREMENTS`` — ticket-keyed registry declaring the
  capabilities a metric consumes. Future metric tickets (M-004+) add their
  entries here as they land. Empty-ish by design today — this ticket is
  the scaffold, not the consumer.

Helpers:

- :func:`missing_for_source` — capabilities the source *doesn't* emit.
- :func:`session_supports_metric` — can we compute ``metric_id`` on a
  session from ``source``?
- :func:`metrics_available_on` — inverse: which metrics work on a given
  source?

Ticket: M-002.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """Named signals a source may or may not emit.

    The string values are stable wire-format identifiers surfaced on the
    Doctor API. Namespacing (``x.y``) mirrors OTel span-attribute style.
    """

    # --- Payloads for behavioral / insight extraction ------------------
    ASSISTANT_RESPONSE_TEXT = "assistant.response.text"
    USER_PROMPT_TEXT = "user.prompt.text"
    TOOL_INPUT = "tool.input"
    TOOL_OUTPUT = "tool.output"

    # --- Interrupt & permission events ---------------------------------
    USER_INTERRUPT_MARKER = "user.interrupt.marker"
    PERMISSION_OUTCOME = "permission.outcome"

    # --- Token accounting beyond the basic prompt/completion -----------
    TOKEN_CACHE_READ = "token.cache_read"
    TOKEN_CACHE_WRITE = "token.cache_write"
    TOKEN_THINKING = "token.thinking"

    # --- Thinking block structure (content and length proxies) ---------
    THINKING_TEXT = "thinking.text"
    THINKING_SIGNATURE = "thinking.signature"

    # --- Harness / configuration attribution ---------------------------
    HARNESS_AGENT_VERSION = "harness.agent_version"
    HARNESS_EFFORT_LEVEL = "harness.effort_level"
    HARNESS_CLAUDE_MD = "harness.claude_md"

    # --- Subagent / sidechain detection --------------------------------
    SUBAGENT_SIDECHAIN = "subagent.sidechain"


#: Human-readable description per capability; surfaced in the Doctor UI
#: so future contributors (and users) understand what's being declared.
CAPABILITY_DESCRIPTIONS: dict[Capability, str] = {
    Capability.ASSISTANT_RESPONSE_TEXT: (
        "Full natural-language response from the agent per turn. Required "
        "for any LLM-classified behavioral signal (ownership-dodge, "
        "reasoning-loop, etc.)."
    ),
    Capability.USER_PROMPT_TEXT: "User's prompt text per turn.",
    Capability.TOOL_INPUT: "Arguments supplied to each tool invocation.",
    Capability.TOOL_OUTPUT: "Output / stderr returned by each tool invocation.",
    Capability.USER_INTERRUPT_MARKER: (
        "Explicit marker that the user cancelled a turn mid-execution "
        "(e.g. `[Request interrupted by user]`)."
    ),
    Capability.PERMISSION_OUTCOME: (
        "Whether the user granted or denied a Permission Request on a tool call."
    ),
    Capability.TOKEN_CACHE_READ: "Prompt-cache read token count per LLM call.",
    Capability.TOKEN_CACHE_WRITE: "Prompt-cache write token count per LLM call.",
    Capability.TOKEN_THINKING: (
        "Separate thinking-token count per LLM call (not lumped into completion)."
    ),
    Capability.THINKING_TEXT: "Raw thinking content when not redacted.",
    Capability.THINKING_SIGNATURE: (
        "Thinking-block signature string — reasoning-depth proxy even when content is redacted."
    ),
    Capability.HARNESS_AGENT_VERSION: (
        "Agent client version (Claude Code / Codex / Copilot release)."
    ),
    Capability.HARNESS_EFFORT_LEVEL: ("Effort setting (low/medium/high/max) per turn or session."),
    Capability.HARNESS_CLAUDE_MD: (
        "Presence and content hash of project CLAUDE.md / memory files."
    ),
    Capability.SUBAGENT_SIDECHAIN: (
        "Whether a session is a sidechain / subagent spawn of a parent session."
    ),
}


#: Per-source declared capability sets.  This is hand-curated, not derived
#: — it reflects what the source *reliably* emits today. Update it when a
#: source gains or loses instrumentation.  When a gap blocks a cinsights
#: metric, it is also cataloged in ``.local/phoenix-gaps.md`` for separate
#: upstream evaluation.
SOURCE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "local": frozenset(
        {
            Capability.ASSISTANT_RESPONSE_TEXT,
            Capability.USER_PROMPT_TEXT,
            Capability.TOOL_INPUT,
            Capability.TOOL_OUTPUT,
            Capability.USER_INTERRUPT_MARKER,
            Capability.PERMISSION_OUTCOME,
            Capability.TOKEN_CACHE_READ,
            Capability.TOKEN_CACHE_WRITE,
            Capability.TOKEN_THINKING,
            Capability.THINKING_TEXT,
            Capability.THINKING_SIGNATURE,
            Capability.HARNESS_AGENT_VERSION,
            Capability.HARNESS_EFFORT_LEVEL,
            Capability.HARNESS_CLAUDE_MD,
            Capability.SUBAGENT_SIDECHAIN,
        }
    ),
    "entireio": frozenset(
        {
            # Entire.io checkpoints include full.jsonl, same richness as local
            # for in-session signals. CLAUDE.md presence is *not* guaranteed
            # because checkpoints may or may not include project memory files
            # depending on commit scope — treated as unavailable for honesty.
            Capability.ASSISTANT_RESPONSE_TEXT,
            Capability.USER_PROMPT_TEXT,
            Capability.TOOL_INPUT,
            Capability.TOOL_OUTPUT,
            Capability.USER_INTERRUPT_MARKER,
            Capability.PERMISSION_OUTCOME,
            Capability.TOKEN_CACHE_READ,
            Capability.TOKEN_CACHE_WRITE,
            Capability.TOKEN_THINKING,
            Capability.THINKING_TEXT,
            Capability.THINKING_SIGNATURE,
            Capability.HARNESS_AGENT_VERSION,
            Capability.HARNESS_EFFORT_LEVEL,
            Capability.SUBAGENT_SIDECHAIN,
        }
    ),
    "phoenix": frozenset(
        {
            # Phoenix via arize-claude-code-plugin is substantially blind for
            # most behavioral / harness signals. Each gap is tracked in
            # `.local/phoenix-gaps.md`. What *is* emitted reliably: tool I/O
            # on spans, user prompt text on turn spans.
            Capability.USER_PROMPT_TEXT,
            Capability.TOOL_INPUT,
            Capability.TOOL_OUTPUT,
        }
    ),
}


#: Per-metric capability requirements. Future metric tickets add their
#: entries here as they ship. Keys are stable identifiers (namespaced by
#: ticket/area) so the Doctor UI can reference them.
#:
#: The two entries below document M-001's cost-attribution capabilities
#: that are already impacted by source gaps: they are not today *consumed*
#: as gating logic, but their presence makes the Doctor UI honest about
#: which sources can deliver accurate cache / thinking token attribution.
METRIC_REQUIREMENTS: dict[str, frozenset[Capability]] = {
    "llm_call_log.cache_tokens": frozenset(
        {
            Capability.TOKEN_CACHE_READ,
            Capability.TOKEN_CACHE_WRITE,
        }
    ),
    "llm_call_log.thinking_tokens": frozenset(
        {
            Capability.TOKEN_THINKING,
        }
    ),
}


def all_known_sources() -> tuple[str, ...]:
    """Stable ordering of the source identifiers we know about."""
    return tuple(SOURCE_CAPABILITIES.keys())


def capabilities_for_source(source: str) -> frozenset[Capability]:
    """Return the capability set for ``source``, or empty if unknown."""
    return SOURCE_CAPABILITIES.get(source, frozenset())


def missing_for_source(source: str) -> frozenset[Capability]:
    """Return capabilities *not* emitted by ``source``.

    Useful for UI surfaces that want to explain why a metric is blank on
    a given session.
    """
    return frozenset(Capability) - capabilities_for_source(source)


def session_supports_metric(source: str, metric_id: str) -> bool:
    """Is ``metric_id`` computable on a session sourced from ``source``?

    Unknown metrics return ``True`` (we assume they have no requirements
    yet); unknown sources return ``False`` (fail-closed on unrecognized).
    """
    required = METRIC_REQUIREMENTS.get(metric_id)
    if required is None:
        return True
    if source not in SOURCE_CAPABILITIES:
        return False
    return required.issubset(SOURCE_CAPABILITIES[source])


def metrics_available_on(source: str) -> frozenset[str]:
    """Return the set of registered ``metric_id``s supported on ``source``."""
    return frozenset(mid for mid in METRIC_REQUIREMENTS if session_supports_metric(source, mid))


def missing_capabilities_for_metric(source: str, metric_id: str) -> frozenset[Capability]:
    """Which capabilities are required by ``metric_id`` but not emitted by ``source``."""
    required = METRIC_REQUIREMENTS.get(metric_id, frozenset())
    return required - capabilities_for_source(source)
