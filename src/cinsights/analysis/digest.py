"""Cross-session digest analysis using 3 concurrent LLM calls."""

from __future__ import annotations

import asyncio
import logging

import anthropic
from pydantic import BaseModel, Field

from cinsights.prompts import render
from cinsights.stats import DigestStats

logger = logging.getLogger(__name__)


# --- Structured output schemas ---


class AtAGlance(BaseModel):
    whats_working: str = Field(description="What interaction patterns are productive")
    whats_hindering: str = Field(description="What recurring friction slows them down")
    quick_wins: str = Field(description="2-3 immediate actionable improvements")
    ambitious_workflows: str = Field(description="Forward-looking automation ideas")


class WorkArea(BaseModel):
    name: str = Field(description="Work area name, e.g. 'PR Reviews'")
    session_count: int = Field(description="Approximate number of sessions")
    description: str = Field(description="2-sentence description of how Claude was used")


class NarrativeResult(BaseModel):
    at_a_glance: AtAGlance
    work_areas: list[WorkArea]
    developer_persona: str = Field(description="2-3 paragraph narrative in markdown")
    fun_ending: str = Field(description="Humorous observation from the data")


class FrictionItem(BaseModel):
    category: str = Field(description="Descriptive category name")
    description: str = Field(description="2-3 sentence explanation of the pattern")
    examples: list[str] = Field(description="Specific evidence from sessions")
    severity: str = Field(description="critical, warning, or info")


class ClaudeMdSuggestion(BaseModel):
    rule: str = Field(description="Copy-paste-ready CLAUDE.md rule")
    why: str = Field(description="Why this rule matters, citing friction evidence")


class FeatureRecommendation(BaseModel):
    feature: str = Field(description="Feature name: Custom Skills, Hooks, Headless Mode, etc.")
    title: str = Field(description="One-line recommendation title")
    why_for_you: str = Field(description="Personalized explanation citing evidence")
    setup_code: str | None = Field(
        default=None, description="Optional setup code block"
    )


class ActionsResult(BaseModel):
    friction_analysis: list[FrictionItem]
    claude_md_suggestions: list[ClaudeMdSuggestion]
    feature_recommendations: list[FeatureRecommendation]


class WinItem(BaseModel):
    title: str
    description: str
    evidence: str = Field(description="Which sessions demonstrate this")


class WorkflowPattern(BaseModel):
    name: str
    description: str
    rationale: str
    starter_prompt: str = Field(description="Copy-paste prompt for Claude Code")


class ForwardResult(BaseModel):
    impressive_wins: list[WinItem]
    workflow_patterns: list[WorkflowPattern]
    ambitious_workflows: list[WorkflowPattern]


# --- Tool definitions for structured output ---

_NARRATIVE_TOOL = {
    "name": "record_narrative",
    "description": "Record the narrative analysis sections of the digest.",
    "input_schema": NarrativeResult.model_json_schema(),
}

_ACTIONS_TOOL = {
    "name": "record_actions",
    "description": "Record friction analysis, CLAUDE.md suggestions, and feature recommendations.",
    "input_schema": ActionsResult.model_json_schema(),
}

_FORWARD_TOOL = {
    "name": "record_forward",
    "description": "Record wins, workflow patterns, and ambitious workflow ideas.",
    "input_schema": ForwardResult.model_json_schema(),
}


class DigestAnalysisResult(BaseModel):
    """Combined result from all 3 LLM calls."""

    narrative: NarrativeResult
    actions: ActionsResult
    forward: ForwardResult
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class DigestAnalyzer:
    """Analyze cross-session patterns using 3 concurrent LLM calls."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
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

    async def analyze(self, stats: DigestStats) -> DigestAnalysisResult:
        """Run 3 concurrent LLM calls and combine results."""
        stats_dict = stats.model_dump()

        # Run all 3 analyses concurrently
        narrative_task = self._call_llm(
            system_template="digest_narrative_system.md.j2",
            user_template="digest_narrative_user.md.j2",
            tool=_NARRATIVE_TOOL,
            tool_name="record_narrative",
            result_cls=NarrativeResult,
            template_vars=stats_dict,
        )
        actions_task = self._call_llm(
            system_template="digest_actions_system.md.j2",
            user_template="digest_actions_user.md.j2",
            tool=_ACTIONS_TOOL,
            tool_name="record_actions",
            result_cls=ActionsResult,
            template_vars=stats_dict,
        )
        forward_task = self._call_llm(
            system_template="digest_forward_system.md.j2",
            user_template="digest_forward_user.md.j2",
            tool=_FORWARD_TOOL,
            tool_name="record_forward",
            result_cls=ForwardResult,
            template_vars=stats_dict,
        )

        results = await asyncio.gather(narrative_task, actions_task, forward_task)
        narrative, narrative_usage = results[0]
        actions, actions_usage = results[1]
        forward, forward_usage = results[2]

        total_prompt = sum(u[0] for u in [narrative_usage, actions_usage, forward_usage])
        total_completion = sum(
            u[1] for u in [narrative_usage, actions_usage, forward_usage]
        )

        logger.info(
            "Digest analysis complete: %d prompt + %d completion tokens",
            total_prompt,
            total_completion,
        )

        return DigestAnalysisResult(
            narrative=narrative,
            actions=actions,
            forward=forward,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
        )

    async def _call_llm(
        self,
        system_template: str,
        user_template: str,
        tool: dict,
        tool_name: str,
        result_cls: type[BaseModel],
        template_vars: dict,
    ) -> tuple[BaseModel, tuple[int, int]]:
        """Make a single LLM call with structured output."""
        system_prompt = render(system_template)
        user_prompt = render(user_template, **template_vars)

        logger.info("Digest LLM call: %s (~%d chars)", tool_name, len(user_prompt))

        response = await self.async_client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
        )

        usage = (response.usage.input_tokens, response.usage.output_tokens)

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return result_cls.model_validate(block.input), usage

        logger.error("No tool_use block for %s", tool_name)
        raise ValueError(f"No structured output from {tool_name}")
