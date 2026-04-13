"""Tests for local source project name derivation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cinsights.sources.local.source import (
    _project_from_cc_slug,
    _project_from_codex_head,
    _resolve_slug_path,
    _slug_name_variants,
)


def _fake_fs(*existing_dirs: str):
    """Return a patch that makes Path.is_dir() true for the listed paths."""
    real_set = {str(Path(d)) for d in existing_dirs}

    def _is_dir(self: Path) -> bool:
        return str(self) in real_set

    return patch.object(Path, "is_dir", _is_dir)


class TestSlugNameVariants:
    def test_plain_name(self):
        assert _slug_name_variants("myproject") == ["myproject"]

    def test_dashed_name(self):
        v = _slug_name_variants("my-cool-app")
        assert v == ["my-cool-app", "my.cool.app"]

    def test_single_dash(self):
        v = _slug_name_variants("foo-bar")
        assert v == ["foo-bar", "foo.bar"]

    def test_no_dashes(self):
        v = _slug_name_variants("nodashes")
        assert v == ["nodashes"]


class TestResolveSlugPath:
    def test_simple_path(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/myproject"):
            result = _resolve_slug_path("-Users-alice-repos-acme-myproject")
            assert result == Path("/Users/alice/repos/acme/myproject")
            assert result.name == "myproject"

    def test_dashed_dirname(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/my-cool-app"):
            result = _resolve_slug_path("-Users-alice-repos-acme-my-cool-app")
            assert result == Path("/Users/alice/repos/acme/my-cool-app")

    def test_dotted_dirname(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/alice.github.io"):
            result = _resolve_slug_path("-Users-alice-repos-acme-alice-github-io")
            assert result == Path("/Users/alice/repos/acme/alice.github.io")

    def test_prefers_dash_over_dot(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme",
                       "/Users/alice/repos/acme/my-app",
                       "/Users/alice/repos/acme/my.app"):
            result = _resolve_slug_path("-Users-alice-repos-acme-my-app")
            assert result == Path("/Users/alice/repos/acme/my-app")

    def test_greedy_longest_match(self):
        with _fake_fs("/a", "/a/foo-bar-baz"):
            result = _resolve_slug_path("-a-foo-bar-baz")
            assert result == Path("/a/foo-bar-baz")

    def test_returns_none_for_nonexistent(self):
        with _fake_fs():
            result = _resolve_slug_path("-does-not-exist")
            assert result is None

    def test_partial_resolution(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos"):
            result = _resolve_slug_path("-Users-alice-repos-deleted-project")
            assert result == Path("/Users/alice/repos")

    def test_strips_leading_dashes(self):
        with _fake_fs("/Users", "/Users/alice"):
            result = _resolve_slug_path("---Users-alice")
            assert result == Path("/Users/alice")

    def test_deeply_nested(self):
        with _fake_fs("/a", "/a/b", "/a/b/c", "/a/b/c/d", "/a/b/c/d/project"):
            result = _resolve_slug_path("-a-b-c-d-project")
            assert result == Path("/a/b/c/d/project")


class TestProjectFromCcSlug:
    def test_standard_slug(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/myproject"):
            assert _project_from_cc_slug("-Users-alice-repos-acme-myproject") == "myproject"

    def test_worktree_suffix_stripped(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/myproject"):
            slug = "-Users-alice-repos-acme-myproject--claude-worktrees-feat-new-feature"
            assert _project_from_cc_slug(slug) == "myproject"

    def test_multiple_double_dash_segments(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/proj"):
            slug = "-Users-alice-repos-acme-proj--foo--bar"
            assert _project_from_cc_slug(slug) == "proj"

    def test_dotted_directory_name(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/alice.github.io"):
            assert _project_from_cc_slug("-Users-alice-repos-acme-alice-github-io") == "alice.github.io"

    def test_dashed_directory_name(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/my-cool-app"):
            assert _project_from_cc_slug("-Users-alice-repos-acme-my-cool-app") == "my-cool-app"

    def test_fallback_when_path_gone(self):
        with _fake_fs():
            assert _project_from_cc_slug("-Users-alice-repos-acme-myproject") == "myproject"

    def test_fallback_with_worktree_suffix(self):
        with _fake_fs():
            slug = "-Users-alice-repos-acme-myproject--claude-worktrees-fix-bug"
            assert _project_from_cc_slug(slug) == "myproject"

    def test_single_component(self):
        with _fake_fs():
            assert _project_from_cc_slug("-myproject") == "myproject"

    def test_empty_slug(self):
        assert _project_from_cc_slug("") is None
        assert _project_from_cc_slug("---") is None

    def test_org_with_dashes(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/my-company",
                       "/Users/alice/repos/my-company/backend"):
            assert _project_from_cc_slug("-Users-alice-repos-my-company-backend") == "backend"

    def test_nested_repo_path(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/infra",
                       "/Users/alice/repos/acme/infra/deploy-tools"):
            slug = "-Users-alice-repos-acme-infra-deploy-tools"
            assert _project_from_cc_slug(slug) == "deploy-tools"

    def test_worktree_with_dotted_project(self):
        with _fake_fs("/Users", "/Users/alice", "/Users/alice/repos",
                       "/Users/alice/repos/acme", "/Users/alice/repos/acme/acme.dev"):
            slug = "-Users-alice-repos-acme-acme-dev--claude-worktrees-fix-typo"
            assert _project_from_cc_slug(slug) == "acme.dev"


class TestProjectFromCodexHead:
    def _make_head(self, *lines: dict) -> bytes:
        import json
        return b"\n".join(json.dumps(line).encode() for line in lines)

    def test_extracts_from_cwd(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/Users/alice/repos/acme/backend"}},
        )
        assert _project_from_codex_head(head) == "backend"

    def test_strips_trailing_slash(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/Users/alice/repos/acme/backend/"}},
        )
        assert _project_from_codex_head(head) == "backend"

    def test_deeply_nested_cwd(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/a/b/c/d/my-project"}},
        )
        assert _project_from_codex_head(head) == "my-project"

    def test_root_cwd(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/"}},
        )
        assert _project_from_codex_head(head) is None

    def test_no_session_meta(self):
        head = self._make_head(
            {"type": "response_item", "payload": {"role": "user"}},
            {"type": "event_msg", "payload": {"type": "token_count"}},
        )
        assert _project_from_codex_head(head) is None

    def test_session_meta_without_cwd(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"originator": "codex-linux"}},
        )
        assert _project_from_codex_head(head) is None

    def test_session_meta_with_empty_cwd(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": ""}},
        )
        assert _project_from_codex_head(head) is None

    def test_session_meta_not_first_line(self):
        head = self._make_head(
            {"type": "event_msg", "payload": {"type": "start"}},
            {"type": "event_msg", "payload": {"type": "init"}},
            {"type": "session_meta", "payload": {"cwd": "/home/bob/projects/api-server"}},
        )
        assert _project_from_codex_head(head) == "api-server"

    def test_ignores_malformed_json_lines(self):
        raw = b"not json at all\n" + self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/repos/myapp"}},
        )
        assert _project_from_codex_head(raw) == "myapp"

    def test_empty_input(self):
        assert _project_from_codex_head(b"") is None
        assert _project_from_codex_head(b"\n\n\n") is None

    def test_cwd_with_spaces(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/Users/alice/My Projects/cool app"}},
        )
        assert _project_from_codex_head(head) == "cool app"

    def test_cwd_single_component(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/myproject"}},
        )
        assert _project_from_codex_head(head) == "myproject"

    def test_only_first_session_meta_used(self):
        head = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/repos/first"}},
            {"type": "session_meta", "payload": {"cwd": "/repos/second"}},
        )
        assert _project_from_codex_head(head) == "first"

    def test_session_meta_beyond_20_lines_ignored(self):
        filler = [{"type": "event_msg", "payload": {}}] * 25
        filler_bytes = self._make_head(*filler)
        meta = self._make_head(
            {"type": "session_meta", "payload": {"cwd": "/repos/hidden"}},
        )
        head = filler_bytes + b"\n" + meta
        assert _project_from_codex_head(head) is None

    def test_payload_missing(self):
        head = self._make_head({"type": "session_meta"})
        assert _project_from_codex_head(head) is None
