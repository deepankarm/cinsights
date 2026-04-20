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
    for cap in Capability:
        assert cap in CAPABILITY_DESCRIPTIONS
        assert CAPABILITY_DESCRIPTIONS[cap].strip()


def test_known_sources():
    assert set(all_known_sources()) == {"local", "phoenix", "entireio"}


def test_source_capability_sets_are_valid():
    all_caps = set(Capability)
    for caps in SOURCE_CAPABILITIES.values():
        assert caps.issubset(all_caps)


def test_phoenix_missing_assistant_response_text():
    assert Capability.ASSISTANT_RESPONSE_TEXT not in capabilities_for_source("phoenix")
    assert Capability.ASSISTANT_RESPONSE_TEXT in capabilities_for_source("local")
    assert Capability.ASSISTANT_RESPONSE_TEXT in capabilities_for_source("entireio")


def test_missing_is_complement():
    for source in all_known_sources():
        supported = capabilities_for_source(source)
        missing = missing_for_source(source)
        assert supported.isdisjoint(missing)
        assert supported | missing == set(Capability)


def test_unknown_source():
    assert capabilities_for_source("martian") == frozenset()
    assert missing_for_source("martian") == frozenset(Capability)


def test_unknown_metric_passes():
    assert session_supports_metric("local", "not.a.real.metric") is True


def test_unknown_source_fails_known_metric():
    assert session_supports_metric("what", "llm_call_log.cache_tokens") is False


def test_registered_requirements_are_valid():
    all_caps = set(Capability)
    for reqs in METRIC_REQUIREMENTS.values():
        assert reqs.issubset(all_caps)


def test_phoenix_missing_cache_tokens():
    assert session_supports_metric("phoenix", "llm_call_log.cache_tokens") is False
    missing = missing_capabilities_for_metric("phoenix", "llm_call_log.cache_tokens")
    assert Capability.TOKEN_CACHE_READ in missing
    assert Capability.TOKEN_CACHE_WRITE in missing


def test_local_satisfies_all_registered_metrics():
    for mid in METRIC_REQUIREMENTS:
        assert session_supports_metric("local", mid) is True


def test_metrics_available_matches_supports():
    for source in all_known_sources():
        by_iteration = {m for m in METRIC_REQUIREMENTS if session_supports_metric(source, m)}
        assert metrics_available_on(source) == by_iteration
