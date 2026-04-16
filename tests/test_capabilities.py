"""Tests for the source-capability matrix and metric requirement registry
(ticket M-002).
"""

from cinsights.capabilities import (
    CAPABILITY_DESCRIPTIONS,
    METRIC_REQUIREMENTS,
    SOURCE_CAPABILITIES,
    Capability,
    all_known_sources,
    capabilities_for_source,
    metrics_available_on,
    missing_capabilities_for_metric,
    missing_for_source,
    session_supports_metric,
)


def test_every_capability_has_a_description():
    """Missing a description is always an oversight — guard against it."""
    for cap in Capability:
        assert cap in CAPABILITY_DESCRIPTIONS, f"no description for {cap.value}"
        assert CAPABILITY_DESCRIPTIONS[cap].strip(), f"empty description for {cap.value}"


def test_known_sources_cover_all_three_current_adapters():
    assert set(all_known_sources()) == {"local", "phoenix", "entireio"}


def test_source_capability_sets_are_subsets_of_vocabulary():
    all_caps = set(Capability)
    for source, caps in SOURCE_CAPABILITIES.items():
        assert caps.issubset(all_caps), f"{source} declared unknown capability"


def test_phoenix_is_missing_assistant_response_text():
    """Regression guard — this is the most load-bearing Phoenix gap (per
    `.local/phoenix-gaps.md`) and is the single reason BehavioralEvidence
    can't run on Phoenix-sourced sessions."""
    assert Capability.ASSISTANT_RESPONSE_TEXT not in capabilities_for_source("phoenix")
    assert Capability.ASSISTANT_RESPONSE_TEXT in capabilities_for_source("local")
    assert Capability.ASSISTANT_RESPONSE_TEXT in capabilities_for_source("entireio")


def test_missing_for_source_is_complement():
    for source in all_known_sources():
        supported = capabilities_for_source(source)
        missing = missing_for_source(source)
        assert supported.isdisjoint(missing)
        assert supported | missing == set(Capability)


def test_unknown_source_has_empty_capabilities_and_all_missing():
    assert capabilities_for_source("martian") == frozenset()
    assert missing_for_source("martian") == frozenset(Capability)


def test_session_supports_metric_unknown_metric_is_permissive():
    """Unknown metrics fall through to supported — prevents forcing every
    code path to pre-register a metric_id before being callable."""
    assert session_supports_metric("local", "not.a.real.metric") is True


def test_session_supports_metric_unknown_source_is_closed():
    """Unknown sources fail closed for registered metrics — safer than
    guessing."""
    assert session_supports_metric("what", "llm_call_log.cache_tokens") is False


def test_registered_metric_requires_are_subset_of_vocabulary():
    all_caps = set(Capability)
    for mid, reqs in METRIC_REQUIREMENTS.items():
        assert reqs.issubset(all_caps), f"{mid} requires unknown capability"


def test_phoenix_missing_cache_tokens_for_m_001_metric():
    """Documents the M-001 honesty path: Phoenix can't satisfy cache
    token attribution."""
    assert session_supports_metric("phoenix", "llm_call_log.cache_tokens") is False
    missing = missing_capabilities_for_metric("phoenix", "llm_call_log.cache_tokens")
    assert Capability.TOKEN_CACHE_READ in missing
    assert Capability.TOKEN_CACHE_WRITE in missing


def test_local_satisfies_all_registered_metrics():
    """If this fails, LocalSource has lost capability parity with
    entireio — probably unintentional."""
    for mid in METRIC_REQUIREMENTS:
        assert session_supports_metric("local", mid) is True


def test_metrics_available_on_matches_session_supports():
    for source in all_known_sources():
        by_iteration = {m for m in METRIC_REQUIREMENTS if session_supports_metric(source, m)}
        assert metrics_available_on(source) == by_iteration
