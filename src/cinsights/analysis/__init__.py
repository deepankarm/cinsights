"""LLM-based analysis: session insights, digest generation, project detection.

All analyzers inherit from ``LLMAnalyzer`` which holds a pydantic-ai model
and provides ``_run_llm`` — the shared call primitive that creates an Agent,
runs it, and returns structured output + token usage.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMAnalyzer:
    """Base class for all pydantic-ai backed analyzers."""

    def __init__(self, model):
        """Initialize with a pydantic-ai model instance (e.g. AnthropicModel)."""
        self.model = model

    async def _run_llm(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> tuple[T, int, int]:
        """Run a single pydantic-ai Agent call.

        Returns (output, prompt_tokens, completion_tokens).
        """
        agent = Agent(
            self.model,
            output_type=output_type,
            system_prompt=system_prompt,
            model_settings=ModelSettings(max_tokens=max_tokens),
            instrument=False,
        )
        result = await agent.run(user_prompt)
        usage = result.usage()
        return result.output, usage.input_tokens or 0, usage.output_tokens or 0
