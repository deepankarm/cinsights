"""Tests for JSONL parsing utilities and Claude Code session parser."""

import json
from datetime import UTC, datetime

from cinsights.sources.jsonl_utils import (
    extract_tool_results,
    extract_user_content,
    group_into_turns,
    parse_dt,
    parse_lines,
)

# --- parse_dt ---


def test_parse_dt_z_suffix():
    result = parse_dt("2026-04-01T10:30:00Z")
    assert result == datetime(2026, 4, 1, 10, 30, 0, tzinfo=UTC)


def test_parse_dt_offset():
    result = parse_dt("2026-04-01T10:30:00+00:00")
    assert result == datetime(2026, 4, 1, 10, 30, 0, tzinfo=UTC)


def test_parse_dt_with_millis():
    result = parse_dt("2026-04-01T10:30:00.123Z")
    assert result.year == 2026
    assert result.second == 0


# --- extract_user_content ---


def test_extract_user_content_string():
    assert extract_user_content({"content": "hello"}) == "hello"


def test_extract_user_content_text_blocks():
    msg = {"content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "x"}]}
    assert extract_user_content(msg) == "hi"


def test_extract_user_content_string_blocks():
    msg = {"content": ["line1", "line2"]}
    assert extract_user_content(msg) == "line1\nline2"


def test_extract_user_content_empty_list():
    assert extract_user_content({"content": []}) == ""


def test_extract_user_content_missing():
    assert extract_user_content({}) == ""


# --- extract_tool_results ---


def test_extract_tool_results_with_results():
    msg = {
        "content": [
            {"type": "tool_result", "tool_use_id": "abc", "content": "ok"},
            {"type": "tool_result", "tool_use_id": "def", "content": "done"},
            {"type": "text", "text": "hello"},
        ]
    }
    results = extract_tool_results(msg)
    assert len(results) == 2
    assert "abc" in results
    assert "def" in results


def test_extract_tool_results_none():
    assert extract_tool_results({"content": [{"type": "text", "text": "hi"}]}) == {}


def test_extract_tool_results_string_content():
    assert extract_tool_results({"content": "just text"}) == {}


def test_extract_tool_results_no_content():
    assert extract_tool_results({}) == {}


# --- parse_lines ---


def _jsonl(*dicts):
    return b"\n".join(json.dumps(d).encode() for d in dicts)


def test_parse_lines_filters_skip_types():
    data = _jsonl(
        {"type": "user", "message": {"content": "hi"}},
        {"type": "progress", "data": "loading"},
        {"type": "system", "data": "init"},
        {"type": "assistant", "message": {"content": "hello"}},
    )
    lines = parse_lines(data)
    assert len(lines) == 2
    assert lines[0]["type"] == "user"
    assert lines[1]["type"] == "assistant"


def test_parse_lines_skips_invalid_json():
    data = b'{"type": "user"}\nnot json at all\n{"type": "assistant"}'
    lines = parse_lines(data)
    assert len(lines) == 2


def test_parse_lines_skips_non_dict():
    data = b'[1, 2, 3]\n{"type": "user"}'
    lines = parse_lines(data)
    assert len(lines) == 1


def test_parse_lines_empty():
    assert parse_lines(b"") == []


def test_parse_lines_skips_snapshots():
    data = _jsonl({"snapshot": {}, "messageId": "abc"}, {"type": "user"})
    lines = parse_lines(data)
    assert len(lines) == 1


# --- group_into_turns ---


def test_group_into_turns_basic():
    lines = [
        {"type": "user", "message": {"content": "do something"}},
        {"type": "assistant", "message": {"content": "ok"}},
        {"type": "user", "message": {"content": "next task"}},
        {"type": "assistant", "message": {"content": "done"}},
    ]
    turns = group_into_turns(lines)
    assert len(turns) == 2
    assert turns[0]["user"]["type"] == "user"
    assert len(turns[0]["assistants"]) == 1
    assert len(turns[1]["assistants"]) == 1


def test_group_into_turns_multiple_assistants():
    lines = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"content": "thinking..."}},
        {"type": "assistant", "message": {"content": "done"}},
    ]
    turns = group_into_turns(lines)
    assert len(turns) == 1
    assert len(turns[0]["assistants"]) == 2


def test_group_into_turns_tool_results_merged():
    lines = [
        {"type": "user", "message": {"content": "start"}},
        {"type": "assistant", "message": {"content": "calling tool"}},
        {
            "type": "user",
            "timestamp": "2026-04-01T10:00:00Z",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        },
    ]
    turns = group_into_turns(lines)
    assert len(turns) == 1  # tool result merged into existing turn
    assert "t1" in turns[0]["tool_results"]


def test_group_into_turns_assistant_only():
    lines = [
        {"type": "assistant", "message": {"content": "unprompted"}},
    ]
    turns = group_into_turns(lines)
    assert len(turns) == 1
    assert turns[0]["user"] is None


def test_group_into_turns_empty():
    assert group_into_turns([]) == []


# --- Claude Code parser integration ---


def test_parse_claude_code_minimal():
    """Minimal JSONL with one turn and one tool call."""
    from cinsights.sources.local.parsers.claude_code import parse_claude_code

    lines = [
        {
            "type": "user",
            "timestamp": "2026-04-01T10:00:00Z",
            "message": {"role": "user", "content": "read the file"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-04-01T10:00:05Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool1",
                        "name": "Read",
                        "input": {"file_path": "/a.py"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "timestamp": "2026-04-01T10:00:06Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool1",
                        "content": "file contents here",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-04-01T10:00:10Z",
            "message": {"role": "assistant", "content": "Here's the file."},
        },
    ]
    data = b"\n".join(json.dumps(line).encode() for line in lines)
    trace, spans = parse_claude_code(data, trace_id="test-1", user_id="user1", project_name="proj")

    assert trace.trace_id == "test-1"
    assert len(spans) > 0

    # Should have a root span, turn span, and tool span
    tool_spans = [s for s in spans if s.tool_name == "Read"]
    assert len(tool_spans) == 1
    assert tool_spans[0].is_success is True


def test_parse_claude_code_empty():
    from cinsights.sources.local.parsers.claude_code import parse_claude_code

    trace, spans = parse_claude_code(b"", trace_id="empty", user_id=None, project_name=None)
    assert trace.trace_id == "empty"
    assert len(spans) == 0
