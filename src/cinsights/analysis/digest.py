"""Cross-session digest analysis using 3 concurrent LLM calls."""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from cinsights.analysis import LLMAnalyzer
from cinsights.prompts import render
from cinsights.settings import PromptTemplates
from cinsights.stats import DigestStats

logger = logging.getLogger(__name__)


class AtAGlance(BaseModel):
    whats_working: list[str] = Field(
        description="2-4 crisp one-sentence bullets on productive patterns",
    )
    whats_hindering: list[str] = Field(
        description="2-4 crisp one-sentence bullets on friction, with numbers",
    )
    quick_wins: list[str] = Field(
        description="2-3 immediate actionable improvements for TODAY",
    )
    ambitious_workflows: list[str] = Field(
        description="2-3 forward-looking automation ideas",
    )


class WorkArea(BaseModel):
    name: str = Field(description="Work area name, e.g. 'PR Reviews'")
    session_count: int = Field(description="Approximate number of sessions")
    description: str = Field(description="2-sentence description of how Claude was used")


class NarrativeResult(BaseModel):
    at_a_glance: AtAGlance
    work_areas: list[WorkArea]
    developer_persona: str = Field(description="2-3 paragraph narrative in markdown")


class FrictionItem(BaseModel):
    category: str = Field(description="Descriptive category name")
    description: str = Field(description="2-3 sentence explanation of the pattern")
    examples: list[str] = Field(description="Specific evidence from sessions")
    severity: str = Field(description="critical, warning, or info")
    estimated_impact: str = Field(
        default="",
        description="Rough time/cost impact with reasoning, e.g. '~2-4 hours/month based on 12 occurrences x ~15min recovery each. Calculation is approximate.'",
    )


class ClaudeMdSuggestion(BaseModel):
    rule: str = Field(description="Copy-paste-ready CLAUDE.md rule")
    why: str = Field(description="Why this rule matters, citing friction evidence")


class FeatureRecommendation(BaseModel):
    feature: str = Field(
        description="Feature name: Custom Skills, Hooks, Headless Mode, Sub-agents, Plan Mode"
    )
    title: str = Field(description="One-line recommendation title")
    why_for_you: str = Field(description="Personalized explanation citing evidence from sessions")
    setup_code: str | None = Field(
        default=None, description="Working config, skill prompt, or hook definition — ready to use"
    )


class ActionsResult(BaseModel):
    friction_analysis: list[FrictionItem]
    claude_md_suggestions: list[ClaudeMdSuggestion]
    feature_recommendations: list[FeatureRecommendation]


class WinItem(BaseModel):
    title: str
    description: str
    evidence: str = Field(description="Which sessions demonstrate this")


class Recommendation(BaseModel):
    name: str
    description: str = Field(description="What to do and why")
    rationale: str = Field(description="Evidence from sessions")
    starter_prompt: str | None = Field(default=None, description="Copy-paste prompt if applicable")
    difficulty: str = Field(
        default="moderate",
        description="'quick' (do today), 'moderate' (this week), or 'ambitious' (project)",
    )


class ForwardResult(BaseModel):
    impressive_wins: list[WinItem]
    recommendations: list[Recommendation] = Field(
        description="3-6 workflow improvements, ordered from quick wins to ambitious ideas"
    )


class DigestAnalysisResult(BaseModel):
    """Combined result from all 3 LLM calls."""

    narrative: NarrativeResult
    actions: ActionsResult
    forward: ForwardResult
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class DigestAnalyzer(LLMAnalyzer):
    """Analyze cross-session patterns using 3 concurrent LLM calls."""

    async def analyze(
        self, stats: DigestStats, *, digest_id: str | None = None
    ) -> DigestAnalysisResult:
        """Run 3 concurrent LLM calls and combine results.

        ``digest_id`` is threaded into each ``LLMCallLog`` row as the
        ``scope_id`` so per-digest cost attribution works.
        """
        from cinsights.db.models import LLMCallKind
        from cinsights.settings import get_config

        limits = get_config().limits

        stats_dict = stats.model_dump()
        stats_dict["max_health"] = limits.max_digest_session_health

        # Run all 3 analyses concurrently
        narrative_task = self._call_llm(
            system_template=PromptTemplates.DIGEST_NARRATIVE_SYSTEM,
            user_template=PromptTemplates.DIGEST_NARRATIVE_USER,
            result_cls=NarrativeResult,
            template_vars=stats_dict,
            call_kind=LLMCallKind.DIGEST_NARRATIVE,
            scope_id=digest_id,
        )
        actions_task = self._call_llm(
            system_template=PromptTemplates.DIGEST_ACTIONS_SYSTEM,
            user_template=PromptTemplates.DIGEST_ACTIONS_USER,
            result_cls=ActionsResult,
            template_vars=stats_dict,
            call_kind=LLMCallKind.DIGEST_ACTIONS,
            scope_id=digest_id,
        )
        forward_task = self._call_llm(
            system_template=PromptTemplates.DIGEST_FORWARD_SYSTEM,
            user_template=PromptTemplates.DIGEST_FORWARD_USER,
            result_cls=ForwardResult,
            template_vars=stats_dict,
            call_kind=LLMCallKind.DIGEST_FORWARD,
            scope_id=digest_id,
        )

        results = await asyncio.gather(narrative_task, actions_task, forward_task)
        narrative, narrative_usage = results[0]
        actions, actions_usage = results[1]
        forward, forward_usage = results[2]

        total_prompt = sum(u[0] for u in [narrative_usage, actions_usage, forward_usage])
        total_completion = sum(u[1] for u in [narrative_usage, actions_usage, forward_usage])

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
        result_cls: type[BaseModel],
        template_vars: dict,
        *,
        call_kind,
        scope_id: str | None = None,
    ) -> tuple[BaseModel, tuple[int, int]]:
        """Make a single LLM call with structured output."""
        from cinsights.db.models import LLMCallScopeType

        system_prompt = render(system_template)
        user_prompt = render(user_template, **template_vars)

        logger.info("Digest LLM call: %s (~%d chars)", result_cls.__name__, len(user_prompt))

        output, prompt_tokens, completion_tokens = await self._run_llm(
            result_cls,
            system_prompt,
            user_prompt,
            call_kind=call_kind,
            scope_type=LLMCallScopeType.DIGEST if scope_id else LLMCallScopeType.UNKNOWN,
            scope_id=scope_id,
            max_tokens=8192,
        )
        return output, (prompt_tokens, completion_tokens)
