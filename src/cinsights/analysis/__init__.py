"""LLM-based analysis: session insights, digest generation, project detection.

Ollama uses response_format=json_schema directly because pydantic-ai's
tool-calling is unreliable on local models (pydantic-ai#4160).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from cinsights.db.models import LLMCallKind, LLMCallScopeType, LLMCallStatus

if TYPE_CHECKING:
    from cinsights.settings import LLMConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def _persist_llm_call(
    *,
    call_kind: LLMCallKind,
    scope_type: LLMCallScopeType,
    scope_id: str | None,
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: float,
    status: LLMCallStatus,
    error_message: str | None,
) -> None:
    """Log one LLM call. Swallows its own errors — observability must not break the pipeline."""
    try:
        from cinsights.costs import estimate_cost
        from cinsights.db.engine import get_sessionmaker
        from cinsights.db.models import LLMCallLog
        from cinsights.settings import get_settings

        dollar_cost = (
            estimate_cost(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                model=model,
                provider=provider,
            )
            if status == LLMCallStatus.SUCCESS and prompt_tokens > 0
            else None
        )

        settings = get_settings()
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            row = LLMCallLog(
                tenant_id=settings.tenant_id,
                call_kind=call_kind,
                scope_type=scope_type,
                scope_id=scope_id,
                model=model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message[:2000] if error_message else None,
                dollar_cost=dollar_cost,
            )
            db.add(row)
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist LLMCallLog row: %s", exc)


class LLMAnalyzer:
    def __init__(self, llm_config: LLMConfig):
        self._llm_config = llm_config
        self._model = llm_config.build_model()

    async def _run_llm(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        *,
        call_kind: LLMCallKind,
        scope_type: LLMCallScopeType = LLMCallScopeType.UNKNOWN,
        scope_id: str | None = None,
        max_tokens: int = 4096,
    ) -> tuple[T, int, int]:
        """Returns (output, prompt_tokens, completion_tokens). Logs to LLMCallLog."""
        start = time.perf_counter()
        prompt_tokens = completion_tokens = 0
        status = LLMCallStatus.SUCCESS
        error_message: str | None = None

        try:
            if self._llm_config.is_local_ollama:
                output, prompt_tokens, completion_tokens = await self._run_ollama_direct(
                    output_type, system_prompt, user_prompt, max_tokens
                )
            else:
                output, prompt_tokens, completion_tokens = await self._run_pydantic_ai(
                    output_type, system_prompt, user_prompt, max_tokens
                )
            return output, prompt_tokens, completion_tokens
        except BaseException as exc:
            status = LLMCallStatus.FAILURE
            error_message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            await _persist_llm_call(
                call_kind=call_kind,
                scope_type=scope_type,
                scope_id=scope_id,
                model=self._llm_config.model,
                provider=self._llm_config.provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message,
            )

    async def _run_pydantic_ai(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        _max_retries: int = 3,
    ) -> tuple[T, int, int]:
        agent = Agent(
            self._model,
            output_type=output_type,
            system_prompt=system_prompt,
            retries=5,
            model_settings=ModelSettings(max_tokens=max_tokens),
            instrument=False,
        )
        last_exc: BaseException | None = None
        for attempt in range(_max_retries):
            try:
                result = await agent.run(user_prompt)
                usage = result.usage()
                return result.output, usage.input_tokens or 0, usage.output_tokens or 0
            except Exception as exc:
                exc_str = str(exc)
                is_retryable = "503" in exc_str or "429" in exc_str or "500" in exc_str
                if not is_retryable or attempt == _max_retries - 1:
                    raise
                last_exc = exc
                wait = 2 ** (attempt + 1)  # 2s, 4s
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    _max_retries,
                    wait,
                    exc_str[:80],
                )
                await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _run_ollama_direct(
        self,
        output_type: type[T],
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> tuple[T, int, int]:
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
