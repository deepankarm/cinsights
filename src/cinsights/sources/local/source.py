"""Local filesystem JSONL source for cinsights."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from cinsights.sources.base import DiscoveredSession, SpanData
from cinsights.sources.local.parsers import (
    AgentType,
    detect_agent,
    parse_claude_code,
    parse_codex,
    parse_copilot,
)

logger = logging.getLogger(__name__)


def _project_from_cc_slug(slug: str) -> str | None:
    """Derive project name from a Claude Code project directory slug.

    The slug encodes the full absolute project path with ``/`` replaced by
    ``-``.  E.g. ``-Users-alice-repos-acme-myproject`` for
    ``/Users/alice/repos/acme/myproject``.

    Since directory names can contain literal dashes (``my-cool-app``),
    we walk the real filesystem to find the correct split points.  Worktree
    sub-paths (``--claude-worktrees-*``) are stripped first.
    """
    # Strip worktree / sub-path suffixes (Claude Code uses "--" delimiter)
    base = slug.split("--")[0] if "--" in slug else slug

    resolved = _resolve_slug_path(base)
    if resolved:
        return resolved.name

    # Fallback when the directory no longer exists: last component after
    # the final -repos-<org>- segment.
    parts = base.strip("-").split("-")
    last = parts[-1] if parts else None
    return last or None


def _resolve_slug_path(slug: str) -> Path | None:
    """Walk the filesystem to reconstruct the real path from a slug.

    Claude Code slugs replace both ``/`` and ``.`` with ``-``.  At each level
    we try the longest matching directory name first, testing both dash-literal
    and dot-substituted variants so ``my-site-io`` resolves to
    ``my-site.io`` when that's what exists on disk.
    """
    remaining = slug.lstrip("-")
    current = Path("/")

    while remaining:
        parts = remaining.split("-")
        matched = False
        # Greedy: try longest candidate name first
        for length in range(len(parts), 0, -1):
            candidate_name = "-".join(parts[:length])
            # Try the literal name first, then with dots replacing dashes
            for name in _slug_name_variants(candidate_name):
                candidate_path = current / name
                if candidate_path.is_dir():
                    current = candidate_path
                    remaining = "-".join(parts[length:])
                    matched = True
                    break
            if matched:
                break
        if not matched:
            break

    return current if str(current) != "/" else None


def _slug_name_variants(name: str) -> list[str]:
    """Generate candidate directory names from a slug segment.

    Returns the literal name first, then the fully-dotted variant.
    Only generates the two extremes to keep the search space small.
    """
    variants = [name]
    dotted = name.replace("-", ".")
    if dotted != name:
        variants.append(dotted)
    return variants


def _project_from_codex_head(head: bytes) -> str | None:
    """Extract project name from the first session_meta line's cwd field."""
    for raw_line in head.split(b"\n")[:20]:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "session_meta":
            cwd = obj.get("payload", {}).get("cwd", "").rstrip("/")
            if cwd:
                return cwd.rsplit("/", 1)[-1]
            break
    return None


class LocalSource:
    """Read JSONL session files directly from the local filesystem."""

    source_name = "local"

    def __init__(
        self,
        claude_code_homes: list[Path],
        codex_homes: list[Path],
    ) -> None:
        self.claude_code_homes = claude_code_homes
        self.codex_homes = codex_homes
        self._file_index: dict[str, _FileRef] | None = None
        self._slug_cache: dict[str, str | None] = {}

    def capabilities(self) -> frozenset[str]:
        from cinsights.capabilities import capabilities_for_source

        return frozenset(c.value for c in capabilities_for_source(self.source_name))

    def _build_index(self) -> dict[str, _FileRef]:
        if self._file_index is not None:
            return self._file_index

        index: dict[str, _FileRef] = {}

        # Scan Claude Code homes: <home>/projects/<slug>/**/*.jsonl
        for home in self.claude_code_homes:
            projects_dir = home / "projects"
            if not projects_dir.is_dir():
                logger.debug("Skipping non-existent path: %s", projects_dir)
                continue
            for jsonl_file in projects_dir.rglob("*.jsonl"):
                ref = self._index_cc_file(jsonl_file, projects_dir)
                if ref:
                    index[ref[0]] = ref[1]

        # Scan Codex homes: <home>/sessions/**/*.jsonl
        for home in self.codex_homes:
            sessions_dir = home / "sessions"
            if not sessions_dir.is_dir():
                logger.debug("Skipping non-existent path: %s", sessions_dir)
                continue
            for jsonl_file in sessions_dir.rglob("*.jsonl"):
                ref = self._index_codex_file(jsonl_file)
                if ref:
                    index[ref[0]] = ref[1]

        self._file_index = index
        logger.info(
            "Indexed %d local JSONL files from %d homes",
            len(index),
            len(self.claude_code_homes) + len(self.codex_homes),
        )
        return index

    def _index_cc_file(self, jsonl_file: Path, projects_dir: Path) -> tuple[str, _FileRef] | None:
        """Index a single Claude Code JSONL file."""
        if not jsonl_file.is_file() or jsonl_file.stat().st_size == 0:
            return None
        try:
            head = jsonl_file.read_bytes()[:32768]
        except OSError:
            return None

        agent = detect_agent(head)
        if agent != AgentType.CLAUDE_CODE:
            return None

        # Skip sub-agent sessions (prompt suggestions, compactions, etc.)
        # Sub-agents have isSidechain=true in their JSONL lines.
        import json as json_mod

        for line in head.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json_mod.loads(line)
                if rec.get("isSidechain") is True:
                    return None
                break  # First parseable non-sidechain line means it's a real session
            except (json_mod.JSONDecodeError, ValueError):
                continue

        stem = jsonl_file.stem
        session_id = f"local:{agent}:{stem}"
        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=UTC)

        # The project slug is the first directory component under projects_dir.
        # Files may be nested deeper (e.g. <slug>/<session-id>/subagents/agent-*.jsonl).
        try:
            rel = jsonl_file.relative_to(projects_dir)
            slug = rel.parts[0]
        except (ValueError, IndexError):
            slug = jsonl_file.parent.name

        if slug not in self._slug_cache:
            self._slug_cache[slug] = _project_from_cc_slug(slug)
        project_name = self._slug_cache[slug]

        return session_id, _FileRef(
            path=jsonl_file,
            agent=agent,
            mtime=mtime,
            project_name=project_name,
        )

    def _index_codex_file(self, jsonl_file: Path) -> tuple[str, _FileRef] | None:
        """Index a single Codex JSONL file."""
        if not jsonl_file.is_file() or jsonl_file.stat().st_size == 0:
            return None
        try:
            head = jsonl_file.read_bytes()[:32768]
        except OSError:
            return None

        agent = detect_agent(head)
        if agent != AgentType.CODEX:
            return None

        stem = jsonl_file.stem
        session_id = f"local:{agent}:{stem}"
        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=UTC)

        # Derive project name from session_meta cwd
        project_name = _project_from_codex_head(head)

        return session_id, _FileRef(
            path=jsonl_file,
            agent=agent,
            mtime=mtime,
            project_name=project_name,
        )

    def discover_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[DiscoveredSession]:
        index = self._build_index()
        results = []

        for session_id, ref in index.items():
            if start_time and ref.mtime < start_time:
                continue
            if end_time and ref.mtime > end_time:
                continue

            # Estimate span count from file size (rough: ~500 bytes per line)
            file_size = ref.path.stat().st_size
            estimated_spans = max(file_size // 500, 1)

            results.append(
                DiscoveredSession(
                    session_id=session_id,
                    span_count=estimated_spans,
                    last_span_time=ref.mtime,
                    start_time=ref.mtime,
                    end_time=ref.mtime,
                )
            )

        results.sort(key=lambda s: s.start_time, reverse=True)
        return results

    def get_spans_by_session(self, session_id: str) -> list[SpanData]:
        index = self._build_index()
        ref = index.get(session_id)
        if not ref:
            logger.debug("Session not found in index: %s", session_id)
            return []

        try:
            data = ref.path.read_bytes()
        except OSError:
            logger.exception("Failed to read file: %s", ref.path)
            return []

        user_id = os.environ.get("USER") or Path.home().name

        parsers = {
            AgentType.CLAUDE_CODE: parse_claude_code,
            AgentType.CODEX: parse_codex,
            AgentType.COPILOT: parse_copilot,
        }

        parser = parsers.get(ref.agent)
        if not parser:
            logger.error("No parser for agent type: %s", ref.agent)
            return []

        _, spans = parser(
            data=data,
            trace_id=session_id,
            user_id=user_id,
            project_name=ref.project_name,
        )
        return spans

    def get_agent_type(self, session_id: str) -> str | None:
        index = self._build_index()
        ref = index.get(session_id)
        return ref.agent if ref else None

    def get_project_name(self, session_id: str) -> str | None:
        """Return the derived project name for a session."""
        index = self._build_index()
        ref = index.get(session_id)
        return ref.project_name if ref else None


class _FileRef:
    __slots__ = ("agent", "mtime", "path", "project_name")

    def __init__(
        self,
        path: Path,
        agent: AgentType,
        mtime: datetime,
        project_name: str | None = None,
    ):
        self.path = path
        self.agent = agent
        self.mtime = mtime
        self.project_name = project_name
