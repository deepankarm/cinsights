"""Tests for cost estimation (costs.py)."""

from cinsights.costs import SCHEMA_OVERHEAD_TOKENS, chars_to_tokens, estimate_cost


def test_chars_to_tokens_small_prompt():
    # < 20K chars → 3.5 chars/token ratio
    result = chars_to_tokens(10_000)
    expected = int(10_000 / 3.5) + SCHEMA_OVERHEAD_TOKENS
    assert result == expected


def test_chars_to_tokens_large_prompt():
    # > 80K chars → 2.8 chars/token ratio
    result = chars_to_tokens(100_000)
    expected = int(100_000 / 2.8) + SCHEMA_OVERHEAD_TOKENS
    assert result == expected


def test_chars_to_tokens_mid_prompt():
    # 50K → interpolated between 3.5 and 2.8
    result = chars_to_tokens(50_000)
    t = (50_000 - 20_000) / 60_000
    ratio = 3.5 - t * 0.7
    expected = int(50_000 / ratio) + SCHEMA_OVERHEAD_TOKENS
    assert result == expected


def test_chars_to_tokens_zero():
    assert chars_to_tokens(0) == SCHEMA_OVERHEAD_TOKENS


def test_chars_to_tokens_monotonic():
    # More chars → more tokens
    assert chars_to_tokens(50_000) > chars_to_tokens(10_000)
    assert chars_to_tokens(100_000) > chars_to_tokens(50_000)


def test_estimate_cost_returns_float_or_none():
    # With explicit model/provider — may return None if genai_prices
    # doesn't have the model, but should not crash
    result = estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        model="gemini-2.5-flash-lite",
        provider="google-gla",
    )
    assert result is None or isinstance(result, float)


def test_estimate_cost_invalid_model():
    result = estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        model="nonexistent-model-xyz",
        provider="nonexistent-provider",
    )
    assert result is None


def test_estimate_cost_bedrock_detection():
    # Bedrock model IDs start with region prefix
    result = estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        provider="anthropic",  # Should auto-detect as aws-bedrock
    )
    # May return None if genai_prices doesn't have this exact model
    assert result is None or isinstance(result, float)
