"""Token estimation and cost calculation utilities.

Provides chars-to-tokens conversion calibrated against actual LLM usage,
session analysis token estimation from span data, and dollar cost
estimation via genai-prices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinsights.sources.base import SpanData

# Calibrated from 20 analyzed sessions against actual token counts.
# Code/JSON-heavy content tokenizes at ~2.8 chars/token; prose at ~3.5.
# pydantic-ai adds ~1100 tokens of schema/tool definitions to every call.
SCHEMA_OVERHEAD_TOKENS = 1100
ESTIMATED_RESPONSE_TOKENS = 900


def chars_to_tokens(total_chars: int) -> int:
    """Convert character count to estimated token count.

    Uses a blended chars/token ratio calibrated from real sessions:
    large prompts are code-heavy (~2.8 chars/token), small prompts
    are prose-heavy (~3.5 chars/token). Includes the pydantic-ai
    schema overhead that gets injected into every call.
    """
    if total_chars > 80_000:
        chars_per_token = 2.8
    elif total_chars < 20_000:
        chars_per_token = 3.5
    else:
        # Linear interpolation between 3.5 (at 20K) and 2.8 (at 80K)
        t = (total_chars - 20_000) / 60_000
        chars_per_token = 3.5 - t * 0.7

    return int(total_chars / chars_per_token) + SCHEMA_OVERHEAD_TOKENS


def estimate_cost(input_tokens: int, output_tokens: int = ESTIMATED_RESPONSE_TOKENS) -> float | None:
    """Estimate dollar cost for an LLM call using the configured model.

    Uses genai-prices with the LLM provider and model from config.
    Detects Bedrock model IDs (e.g. us.anthropic.claude-*) and routes
    to the aws-bedrock provider automatically.
    Returns None if pricing info is unavailable.
    """
    try:
        from genai_prices import Usage, calc_price

        from cinsights.settings import get_llm_config

        llm = get_llm_config()
        model = llm.model
        provider = llm.provider

        # Bedrock model IDs start with a region prefix (us., eu., ap.)
        if model.startswith(("us.", "eu.", "ap.")) and ".anthropic." in model:
            provider = "aws-bedrock"

        usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
        price = calc_price(usage, model_ref=model, provider_id=provider)
        return float(price.total_price)
    except Exception:
        return None


def estimate_total_cost(estimated_tokens: int) -> float | None:
    """Estimate dollar cost from a combined prompt+response token estimate.

    Splits the total into prompt and response tokens using
    ESTIMATED_RESPONSE_TOKENS, then looks up pricing.
    """
    prompt_tokens = estimated_tokens - ESTIMATED_RESPONSE_TOKENS
    return estimate_cost(input_tokens=prompt_tokens, output_tokens=ESTIMATED_RESPONSE_TOKENS)


# System prompt is static — measure once
_system_prompt_chars: int | None = None


def estimate_session_analysis_tokens(spans: list[SpanData]) -> int:
    """Estimate total tokens (prompt + response) for analyzing a session.

    Mirrors the session analysis _build_prompts logic: system prompt +
    session overview + tool distribution + user queries + sampled timeline
    with truncated I/O. Uses actual span data to compute real character counts.
    """
    from cinsights.analysis.session import MAX_IO_CHARS, _sample_timeline_spans
    from cinsights.prompts import render
    from cinsights.settings import PromptTemplates

    global _system_prompt_chars
    if _system_prompt_chars is None:
        _system_prompt_chars = len(render(PromptTemplates.SESSION_SYSTEM))

    # Tool spans (same filter as _build_prompts)
    tool_spans = [
        s for s in spans
        if s.parent_id is not None
        and (s.tool_name or "Permission" in s.name or "Notification" in s.name)
    ]
    turn_spans = [s for s in spans if s.name.startswith("Turn ")]

    # Session overview: model, duration, tool count, errors, tokens, start time
    overview_chars = 200

    # Tool distribution: "- tool_name: count\n" per unique tool
    tool_names: dict[str, int] = {}
    for s in tool_spans:
        name = s.tool_name or "unknown"
        tool_names[name] = tool_names.get(name, 0) + 1
    tool_dist_chars = sum(len(f"- {name}: {count}\n") for name, count in tool_names.items())

    # User queries: "- Turn N: <up to 200 chars>\n" per turn
    query_chars = 0
    for ts in turn_spans:
        if ts.input_value and ts.input_value.strip():
            query_chars += len("- Turn X: ") + min(len(ts.input_value.strip()), 200) + 1

    # Timeline section (the big one)
    sampled_spans, _ = _sample_timeline_spans(spans)

    timeline_chars = 0
    for s in sampled_spans:
        line_chars = 60 + len(s.tool_name or "")
        if s.input_value:
            line_chars += 11 + min(len(s.input_value), MAX_IO_CHARS)
        if s.output_value:
            line_chars += 12 + min(len(s.output_value), MAX_IO_CHARS)
        if not s.is_success:
            err = s.attributes.get("status_message", "")
            if err:
                line_chars += 11 + len(err)
        timeline_chars += line_chars

    total_prompt_chars = (
        _system_prompt_chars + overview_chars + tool_dist_chars
        + query_chars + timeline_chars
    )
    return chars_to_tokens(total_prompt_chars) + ESTIMATED_RESPONSE_TOKENS
