"""LLM-based analysis: session insights, digest generation, project detection.

All analyzers inherit from ``LLMAnalyzer`` which holds a pydantic-ai model
and provides ``_run_llm`` — the shared call primitive that creates an Agent,
runs it, and returns structured output + token usage.

When the provider is a local Ollama endpoint, ``_run_llm`` bypasses
pydantic-ai's tool-calling approach (which Ollama doesn't handle reliably)
and instead uses ``response_format: json_schema`` directly.  This will be
removed once pydantic/pydantic-ai#4160 lands upstream.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:
    from cinsights.settings import LLMConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMAnalyzer:
    """Base class for all pydantic-ai backed analyzers."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize with an LLMConfig.

        The config determines whether to use pydantic-ai's Agent (default)
        or Ollama's native json_schema mode for structured output.
        """
        self._llm_config = llm_config
        self._model = llm_config.build_model()

    async def _run_llm(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> tuple[T, int, int]:
        """Run a single LLM call with structured output.

        Returns (output, prompt_tokens, completion_tokens).
        """
        if self._llm_config.is_local_ollama:
            return await self._run_ollama_direct(
                output_type, system_prompt, user_prompt, max_tokens
            )
        return await self._run_pydantic_ai(output_type, system_prompt, user_prompt, max_tokens)

    async def _run_pydantic_ai(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> tuple[T, int, int]:
        """Standard path: use pydantic-ai Agent with tool-calling."""
        agent = Agent(
            self._model,
            output_type=output_type,
            system_prompt=system_prompt,
            retries=5,
            model_settings=ModelSettings(max_tokens=max_tokens),
            instrument=False,
        )
        result = await agent.run(user_prompt)
        usage = result.usage()
        return result.output, usage.input_tokens or 0, usage.output_tokens or 0

    async def _run_ollama_direct(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> tuple[T, int, int]:
        """Ollama path: use response_format json_schema directly.

        Ollama's OpenAI-compatible API supports grammar-enforced JSON output
        via ``response_format: { type: "json_schema", ... }``.  This is more
        reliable than pydantic-ai's tool-calling approach for local models.

        See: https://github.com/pydantic/pydantic-ai/issues/242
        """
        import httpx

        base_url = self._llm_config.base_url
        model_name = self._llm_config.model

        schema = output_type.model_json_schema()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        async with httpx.AsyncClient(base_url=base_url, timeout=600) as client:
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": model_name,
                    "messages": messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": output_type.__name__,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = output_type.model_validate_json(content)
        usage = data.get("usage", {})

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        logger.debug(
            "Ollama direct call: %s — %d→%d tokens",
            output_type.__name__,
            prompt_tokens,
            completion_tokens,
        )

        return parsed, prompt_tokens, completion_tokens
