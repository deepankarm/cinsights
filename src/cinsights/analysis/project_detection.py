"""LLM-based project detection from a session's tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from cinsights.prompts import render
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


_PROJECT_TOOL = {
    "name": "record_project",
    "description": "Record the detected project for a Claude Code session.",
    "input_schema": ProjectGuess.model_json_schema(),
}


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

    system_prompt = render("project_detection_system.md.j2")
    user_prompt = render(
        "project_detection_user.md.j2",
        file_paths=signals["file_paths"],
        bash_commands=signals["bash_commands"],
        tool_counts=signals["tool_counts"],
        known_projects=known_projects,
        previous_guess=previous_guess,
    )
    return system_prompt, user_prompt


class ProjectDetector:
    def __init__(
        self,
        api_key: str,
        model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        self.async_client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model

    async def detect(
        self,
        tool_spans: list[SpanData],
        known_projects: list[str],
        previous_guess: str | None = None,
    ) -> ProjectGuess:
        system_prompt, user_prompt = _build_prompts(
            tool_spans, known_projects, previous_guess
        )

        logger.info(
            "Detecting project (%d tool spans, prompt ~%d chars)",
            len(tool_spans),
            len(user_prompt),
        )

        response = await self.async_client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[_PROJECT_TOOL],
            tool_choice={"type": "tool", "name": "record_project"},
        )

        result = self._parse_response(response)
        result.usage_prompt_tokens = response.usage.input_tokens
        result.usage_completion_tokens = response.usage.output_tokens
        return result

    async def detect_batch(
        self,
        items: list[tuple[str, list[SpanData]]],
        known_projects: list[str],
        max_concurrency: int = 5,
    ) -> list[ProjectGuess]:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(
            previous: str | None, spans: list[SpanData]
        ) -> ProjectGuess:
            async with semaphore:
                return await self.detect(spans, known_projects, previous)

        tasks = [_bounded(prev, spans) for prev, spans in items]
        return await asyncio.gather(*tasks)

    def _parse_response(self, response: anthropic.types.Message) -> ProjectGuess:
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_project":
                return ProjectGuess.model_validate(block.input)

        logger.error("No tool_use block in project detection response")
        return ProjectGuess(
            project_name=None,
            confidence="low",
            reasoning="LLM returned no structured output",
        )
