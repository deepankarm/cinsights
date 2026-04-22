"""Tests for quality metrics computation (metrics.py).

These are the core free-tier metrics — if they're wrong, scoring is wrong,
and analysis selection is wrong.
"""

from types import SimpleNamespace

import pytest

from cinsights.metrics import (
    compute_all,
    context_pressure,
    edits_without_read_pct,
    error_rate,
    read_edit_ratio,
    repeated_edits_to_same_file,
    research_mutation_ratio,
    subagent_spawn_rate,
    tokens_per_useful_edit,
    write_vs_edit_pct,
)


def tc(name, success=True, input_value=None):
    """Create a minimal ToolCall-like object."""
    return SimpleNamespace(tool_name=name, success=success, input_value=input_value)


# --- read_edit_ratio ---


def test_read_edit_ratio_balanced():
    assert read_edit_ratio([tc("Read"), tc("Edit")]) == 1.0


def test_read_edit_ratio_high():
    calls = [tc("Read")] * 6 + [tc("Edit")]
    assert read_edit_ratio(calls) == 6.0


def test_read_edit_ratio_includes_grep_glob():
    # Grep and Glob count as reads
    calls = [tc("Read"), tc("Grep"), tc("Glob"), tc("Edit")]
    assert read_edit_ratio(calls) == 3.0


def test_read_edit_ratio_no_edits():
    assert read_edit_ratio([tc("Read"), tc("Bash")]) is None


def test_read_edit_ratio_empty():
    assert read_edit_ratio([]) is None


# --- edits_without_read_pct ---


def test_edits_without_read_all_blind():
    calls = [tc("Edit", input_value='{"file_path": "/a.py"}')]
    assert edits_without_read_pct(calls) == 100.0


def test_edits_without_read_none_blind():
    calls = [
        tc("Read", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/a.py"}'),
    ]
    assert edits_without_read_pct(calls) == 0.0


def test_edits_without_read_mixed():
    calls = [
        tc("Read", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/b.py"}'),  # blind
    ]
    assert edits_without_read_pct(calls) == 50.0


def test_edits_without_read_no_edits():
    assert edits_without_read_pct([tc("Read")]) is None


# --- research_mutation_ratio ---


def test_research_mutation_ratio_basic():
    calls = [tc("Read"), tc("Grep"), tc("Edit")]
    assert research_mutation_ratio(calls) == 2.0


def test_research_mutation_ratio_with_writes():
    calls = [tc("Read"), tc("Read"), tc("Edit"), tc("Write")]
    assert research_mutation_ratio(calls) == 1.0


def test_research_mutation_ratio_no_mutations():
    assert research_mutation_ratio([tc("Read"), tc("Bash")]) is None


# --- write_vs_edit_pct ---


def test_write_vs_edit_all_writes():
    assert write_vs_edit_pct([tc("Write"), tc("Write")]) == 100.0


def test_write_vs_edit_all_edits():
    assert write_vs_edit_pct([tc("Edit"), tc("Edit")]) == 0.0


def test_write_vs_edit_mixed():
    calls = [tc("Write"), tc("Edit"), tc("Edit")]
    assert write_vs_edit_pct(calls) == pytest.approx(33.3, abs=0.1)


def test_write_vs_edit_no_mutations():
    assert write_vs_edit_pct([tc("Read")]) is None


# --- error_rate ---


def test_error_rate_none_failed():
    assert error_rate([tc("Read"), tc("Edit")]) == 0.0


def test_error_rate_all_failed():
    assert error_rate([tc("Read", success=False)]) == 100.0


def test_error_rate_mixed():
    calls = [tc("Read"), tc("Edit", success=False), tc("Bash", success=False)]
    assert error_rate(calls) == pytest.approx(66.7, abs=0.1)


def test_error_rate_empty():
    assert error_rate([]) is None


# --- repeated_edits_to_same_file ---


def test_repeated_edits_consecutive():
    calls = [
        tc("Edit", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/a.py"}'),
    ]
    assert repeated_edits_to_same_file(calls) == 2


def test_repeated_edits_interrupted():
    calls = [
        tc("Edit", input_value='{"file_path": "/a.py"}'),
        tc("Read", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/a.py"}'),
    ]
    assert repeated_edits_to_same_file(calls) == 0


def test_repeated_edits_different_files():
    calls = [
        tc("Edit", input_value='{"file_path": "/a.py"}'),
        tc("Edit", input_value='{"file_path": "/b.py"}'),
    ]
    assert repeated_edits_to_same_file(calls) == 0


def test_repeated_edits_empty():
    assert repeated_edits_to_same_file([]) == 0


# --- subagent_spawn_rate ---


def test_subagent_spawn_rate_with_agents():
    calls = [tc("Agent"), tc("Agent"), tc("Edit"), tc("Edit"), tc("Edit")]
    assert subagent_spawn_rate(calls) == 40.0


def test_subagent_spawn_rate_none():
    assert subagent_spawn_rate([tc("Edit"), tc("Read")]) == 0.0


def test_subagent_spawn_rate_includes_task():
    calls = [tc("Task"), tc("Edit")]
    assert subagent_spawn_rate(calls) == 50.0


def test_subagent_spawn_rate_empty():
    assert subagent_spawn_rate([]) is None


# --- tokens_per_useful_edit ---


def test_tokens_per_useful_edit_basic():
    calls = [tc("Edit"), tc("Write")]
    assert tokens_per_useful_edit(calls, 1000) == 500.0


def test_tokens_per_useful_edit_failed_excluded():
    calls = [tc("Edit", success=False), tc("Edit")]
    assert tokens_per_useful_edit(calls, 1000) == 1000.0


def test_tokens_per_useful_edit_no_useful():
    calls = [tc("Edit", success=False)]
    assert tokens_per_useful_edit(calls, 1000) is None


def test_tokens_per_useful_edit_zero_tokens():
    assert tokens_per_useful_edit([tc("Edit")], 0) is None


# --- context_pressure ---


def test_context_pressure_all_steep():
    growth = [
        {"prompt_tokens": 100},
        {"prompt_tokens": 200},
        {"prompt_tokens": 400},
    ]
    assert context_pressure(growth) == 1.0


def test_context_pressure_none_steep():
    growth = [
        {"prompt_tokens": 100},
        {"prompt_tokens": 120},
        {"prompt_tokens": 135},
    ]
    assert context_pressure(growth) == 0.0


def test_context_pressure_too_few_turns():
    assert context_pressure([{"prompt_tokens": 100}, {"prompt_tokens": 200}]) is None


def test_context_pressure_none():
    assert context_pressure(None) is None


# --- compute_all ---


def test_compute_all_returns_all_keys():
    calls = [tc("Read"), tc("Edit")]
    growth = [{"prompt_tokens": 100}, {"prompt_tokens": 120}, {"prompt_tokens": 140}]
    result = compute_all(calls, context_growth=growth, total_tokens=500)

    expected_keys = {
        "read_edit_ratio",
        "edits_without_read_pct",
        "research_mutation_ratio",
        "write_vs_edit_pct",
        "error_rate",
        "repeated_edits_count",
        "subagent_spawn_rate",
        "tokens_per_useful_edit",
        "context_pressure_score",
        "turn_count",
        "tool_calls_per_turn",
    }
    assert set(result.keys()) == expected_keys


def test_compute_all_turn_count_from_growth():
    growth = [{"prompt_tokens": 100}] * 5
    result = compute_all([], context_growth=growth)
    assert result["turn_count"] == 5
