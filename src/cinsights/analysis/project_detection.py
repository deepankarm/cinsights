"""LLM-based project detection from a session's tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from cinsights.analysis import LLMAnalyzer
from cinsights.prompts import render
from cinsights.settings import PromptTemplates
from cinsights.sources.base import SpanData

logger = logging.getLogger(__name__)

TOP_FILE_PATHS = 30
TOP_BASH_COMMANDS = 20
BASH_CMD_TRUNCATE = 240
TOP_TOOL_COUNTS = 15

_BASH_INTEREST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcd\s+"),
    re.compile(r"\bpwd\b"),
    re.compile(r"\bgit\s+(status|log|diff|branch|remote|ls-files|rev-parse)"),
    re.compile(r"\bls\s+"),
    re.compile(r"\bcat\s+.*\.(toml|json|mod|yaml|yml|md)"),
    re.compile(r"\bmake\b"),
    re.compile(r"\bnpm\s+(run|install|test|exec)"),
    re.compile(r"\bgo\s+(build|test|run|mod)"),
    re.compile(r"\bcargo\s+(build|test|run)"),
    re.compile(r"\buv\s+run"),
    re.compile(r"\bpytest\b"),
    re.compile(r"\beslint\b"),
    re.compile(r"\bconda\s+activate\b"),
    re.compile(r"\bsource\s+\S+\.env\b"),
]

_FILE_PATH_RE = re.compile(r'"file_path":\s*"([^"]+)"')


class ProjectGuess(BaseModel):
    project_name: str | None = Field(
        description=(
            "Project name (basename of the project root directory). "
            "Use a known project name from the provided list if it matches. "
            "Return null if the session did not work on any clear project — "
            "for example, only edited dotfiles in a home directory, only ran "
            "ad-hoc shell commands, or had no file operations at all."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "high = the project is unambiguous from the evidence. "
            "medium = clear primary candidate but with some noise. "
            "low = the evidence is thin or conflicting."
        )
    )
    reasoning: str = Field(
        description=(
            "One sentence explaining the choice. Cite specific evidence "
            "(file paths, bash commands, manifest files seen)."
        )
    )

    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0


def _extract_file_paths(input_value: str | None) -> list[str]:
    if not input_value:
        return []
    return _FILE_PATH_RE.findall(input_value)


def _extract_bash_command(input_value: str | None) -> str | None:
    if not input_value:
        return None
    try:
        data = json.loads(input_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    cmd = data.get("command") or data.get("cmd")
    if isinstance(cmd, str):
        return cmd.strip()
    return None


def _is_interesting_bash(cmd: str) -> bool:
    return any(p.search(cmd) for p in _BASH_INTEREST_PATTERNS)


def _build_signals(tool_spans: list[SpanData]) -> dict:
    file_path_counts: Counter[str] = Counter()
    bash_commands: list[str] = []
    tool_counts: Counter[str] = Counter()

    for s in tool_spans:
        name = s.tool_name or s.name or "unknown"
        tool_counts[name] += 1

        for fp in _extract_file_paths(s.input_value):
            file_path_counts[fp] += 1

        if name == "Bash":
            cmd = _extract_bash_command(s.input_value)
            if cmd and _is_interesting_bash(cmd):
                if len(cmd) > BASH_CMD_TRUNCATE:
                    cmd = cmd[:BASH_CMD_TRUNCATE] + "..."
                bash_commands.append(cmd)

    return {
        "file_paths": file_path_counts.most_common(TOP_FILE_PATHS),
        "bash_commands": bash_commands[:TOP_BASH_COMMANDS],
        "tool_counts": tool_counts.most_common(TOP_TOOL_COUNTS),
    }


def _build_prompts(
    tool_spans: list[SpanData],
    known_projects: list[str],
    previous_guess: str | None,
) -> tuple[str, str]:
    signals = _build_signals(tool_spans)

    system_prompt = render(PromptTemplates.PROJECT_DETECTION_SYSTEM)
    user_prompt = render(
        PromptTemplates.PROJECT_DETECTION_USER,
        file_paths=signals["file_paths"],
        bash_commands=signals["bash_commands"],
        tool_counts=signals["tool_counts"],
        known_projects=known_projects,
        previous_guess=previous_guess,
    )
    return system_prompt, user_prompt


class ProjectDetector(LLMAnalyzer):
    async def detect(
        self,
        tool_spans: list[SpanData],
        known_projects: list[str],
        previous_guess: str | None = None,
        *,
        scope_id: str | None = None,
    ) -> ProjectGuess:
        from cinsights.db.models import LLMCallKind, LLMCallScopeType

        system_prompt, user_prompt = _build_prompts(tool_spans, known_projects, previous_guess)

        logger.info(
            "Detecting project (%d tool spans, prompt ~%d chars)",
            len(tool_spans),
            len(user_prompt),
        )

        result, prompt_tokens, completion_tokens = await self._run_llm(
            ProjectGuess,
            system_prompt,
            user_prompt,
            max_tokens=512,
            call_kind=LLMCallKind.PROJECT_DETECTION,
            scope_type=LLMCallScopeType.SESSION if scope_id else LLMCallScopeType.UNKNOWN,
            scope_id=scope_id,
        )
        result.usage_prompt_tokens = prompt_tokens
        result.usage_completion_tokens = completion_tokens
        return result

    async def detect_batch(
        self,
        items: list[tuple[str, str | None, list[SpanData]]],
        known_projects: list[str],
        max_concurrency: int = 5,
    ) -> list[ProjectGuess]:
        """Detect projects for a batch of sessions.

        ``items`` is a list of ``(session_id, previous_tag, spans)``. The
        ``session_id`` is threaded through as the ``scope_id`` on the
        ``LLMCallLog`` row so per-session cost attribution works.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(
            session_id: str, previous: str | None, spans: list[SpanData]
        ) -> ProjectGuess:
            async with semaphore:
                return await self.detect(spans, known_projects, previous, scope_id=session_id)

        tasks = [_bounded(sid, prev, spans) for sid, prev, spans in items]
        return await asyncio.gather(*tasks)
