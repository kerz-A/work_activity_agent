"""LiteLLMProvider — единая точка интеграции с LLM (OpenRouter/Groq/Anthropic/OpenAI/...).

Под капотом — LiteLLM, поддерживает structured output через response_format=json_schema.
Retry через tenacity, cost tracking через completion_cost.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from work_activity_agent.config.settings import LLMSettings
from work_activity_agent.domain.errors import LLMResponseValidationError
from work_activity_agent.infrastructure.llm.retry import build_async_retrying
from work_activity_agent.infrastructure.observability.logging import get_logger

T = TypeVar("T", bound=BaseModel)

_log = get_logger("litellm_provider")


def _export_api_keys_to_env(settings: LLMSettings) -> None:
    """LiteLLM читает API ключи / URL из os.environ. Прокидываем из pydantic settings."""
    # Ollama base URL (для локального провайдера)
    os.environ.setdefault("OLLAMA_API_BASE", settings.ollama_base_url)

    mappings = (
        ("OPENROUTER_API_KEY", settings.openrouter_api_key),
        ("GROQ_API_KEY", settings.groq_api_key),
        ("HUGGINGFACE_API_KEY", settings.huggingface_api_key),
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        ("OPENAI_API_KEY", settings.openai_api_key),
    )
    for env_name, secret in mappings:
        if secret is not None and env_name not in os.environ:
            os.environ[env_name] = secret.get_secret_value()


class LiteLLMProvider:
    """Реализация LLMProvider через LiteLLM.

    Маппинг alias → real model берётся из `settings.model_aliases` (configs/models.yaml).
    """

    MAX_VALIDATION_RETRIES = 0  # для маленьких моделей retry только раздувает контекст

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        self._aliases = settings.model_aliases
        self._retrying = build_async_retrying(max_attempts=3)
        self._cost_total_usd: float = 0.0
        _export_api_keys_to_env(settings)

    @property
    def cost_total_usd(self) -> float:
        return self._cost_total_usd

    def resolve_model(self, alias: str) -> str:
        """alias → реальное имя модели LiteLLM."""
        return self._aliases.get(alias, alias)

    async def vision_analyze(
        self,
        image: Path | bytes,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "vision_primary",
        temperature: float = 0.0,
    ) -> T:
        image_b64 = self._encode_image(image)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ]
        return await self._call_with_validation(
            messages=messages,
            response_schema=response_schema,
            model_alias=model_alias,
            temperature=temperature,
        )

    async def classify(
        self,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "text_primary",
        temperature: float = 0.0,
    ) -> T:
        messages = [{"role": "user", "content": prompt}]
        return await self._call_with_validation(
            messages=messages,
            response_schema=response_schema,
            model_alias=model_alias,
            temperature=temperature,
        )

    async def embed(
        self,
        text: str,
        *,
        model_alias: str = "embed_primary",
    ) -> list[float]:
        import litellm

        model = self.resolve_model(model_alias)
        response = await litellm.aembedding(model=model, input=[text])
        first: list[float] = response.data[0]["embedding"]
        return first

    async def _call_with_validation(
        self,
        messages: list[dict[str, Any]],
        response_schema: type[T],
        model_alias: str,
        temperature: float,
    ) -> T:
        """Вызов с retry на сетевые ошибки + retry на ValidationError.

        Сетевые/timeout ошибки оборачиваются в LLMResponseValidationError —
        чтобы узлы могли обработать их единообразно (через except LLMResponseValidationError).
        """
        model = self.resolve_model(model_alias)
        last_validation_error: Exception | None = None

        for validation_attempt in range(self.MAX_VALIDATION_RETRIES + 1):
            try:
                # Жёсткий внешний timeout — LiteLLM может игнорировать свой `timeout` для Ollama.
                content = await asyncio.wait_for(
                    self._call_with_network_retry(
                        model=model,
                        messages=messages,
                        response_schema=response_schema,
                        temperature=temperature,
                    ),
                    timeout=self._settings.request_timeout_s,
                )
            except (TimeoutError, Exception) as e:
                _log.warning(
                    "llm.network_failed",
                    schema=response_schema.__name__,
                    error=str(e)[:200],
                )
                raise LLMResponseValidationError(
                    response_schema.__name__,
                    f"network/timeout: {type(e).__name__}: {e}",
                    attempt=validation_attempt + 1,
                ) from e
            try:
                parsed_obj = json.loads(content)
                return response_schema.model_validate(parsed_obj)
            except (json.JSONDecodeError, ValidationError) as e:
                last_validation_error = e
                _log.warning(
                    "llm.validation_failed",
                    schema=response_schema.__name__,
                    attempt=validation_attempt + 1,
                    error=str(e)[:200],
                )
                # На следующей итерации добавляем feedback
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response failed schema validation: {e}. "
                            f"Return strictly valid JSON matching the schema."
                        ),
                    },
                ]

        raise LLMResponseValidationError(
            response_schema.__name__,
            str(last_validation_error or "unknown"),
            attempt=self.MAX_VALIDATION_RETRIES + 1,
        )

    async def _call_with_network_retry(
        self,
        model: str,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel],
        temperature: float,
    ) -> str:
        """Один вызов LLM с retry на 429/5xx через tenacity."""
        import litellm

        async for attempt in self._retrying:
            with attempt:
                # Используем простой json_object вместо strict json_schema —
                # для маленьких моделей через Ollama strict grammar в 3-5 раз медленнее
                # и часто падает в loop. Схема указывается в промпте, валидация после.
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    timeout=self._settings.request_timeout_s,
                )
                # Cost tracking
                try:
                    cost = litellm.completion_cost(completion_response=response)
                    self._cost_total_usd += float(cost or 0.0)
                    _log.info(
                        "llm.completion",
                        model=model,
                        cost_usd=float(cost or 0.0),
                        cost_total_usd=self._cost_total_usd,
                    )
                except Exception as e:
                    _log.warning("llm.cost_tracking_failed", error=str(e))

                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise LLMResponseValidationError(
                        response_schema.__name__,
                        f"expected string content, got {type(content).__name__}",
                    )
                return content

        raise RuntimeError("retrying loop exited without result (should not happen)")

    @staticmethod
    def _encode_image(image: Path | bytes) -> str:
        if isinstance(image, Path):
            return base64.b64encode(image.read_bytes()).decode("ascii")
        return base64.b64encode(image).decode("ascii")
