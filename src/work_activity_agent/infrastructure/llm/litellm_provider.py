"""LiteLLMProvider — единая точка интеграции с LLM (Ollama / OpenRouter / Anthropic / OpenAI).

Ключевые особенности:
- Для Ollama-моделей включён native constrained decoding по JSON Schema через
  `format=<schema>` (Ollama 0.5+ поддерживает grammar-based generation на уровне токенайзера —
  модель физически не выпустит токен, нарушающий схему). Документация:
  https://docs.ollama.com — раздел "Generate structured JSON with a schema".
- Для cloud-моделей — `response_format={"type": "json_object"}` (плюс инструкция в промпте).
- Validation retry: до 2 повторов с feedback от ошибки в контексте (self-healing pattern).
- Timeout/сетевые ошибки и Pydantic ValidationError разделены — поднимаются разные
  типы исключений (`LLMNetworkError` vs `LLMResponseValidationError`), чтобы метрики
  показывали где именно болит.
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
from work_activity_agent.domain.errors import (
    LLMBudgetExceededError,
    LLMNetworkError,
    LLMResponseValidationError,
)
from work_activity_agent.infrastructure.llm.retry import build_async_retrying
from work_activity_agent.infrastructure.observability.logging import get_logger

T = TypeVar("T", bound=BaseModel)

_log = get_logger("litellm_provider")

_OLLAMA_PREFIXES = ("ollama_chat/", "ollama/")


_PROVIDER_KEY_NAMES = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _detect_used_providers(aliases: dict[str, str]) -> set[str]:
    """По model_aliases определить, ключи каких cloud-провайдеров реально нужны.

    Если aliases пуст (configs не загрузились) — возвращаем все провайдеры
    (fallback на старое поведение, чтобы не сломать запуск).
    """
    if not aliases:
        return set(_PROVIDER_KEY_NAMES.keys())

    used: set[str] = set()
    for model in aliases.values():
        # litellm-формат: "<provider>/<model>" или просто "gpt-4..." (openai default).
        if "/" in model:
            provider = model.split("/", 1)[0].lower()
            # ollama/ollama_chat не требуют API-ключей
            if provider in _PROVIDER_KEY_NAMES:
                used.add(provider)
        elif model.startswith(("gpt-", "o1-", "o3-")):
            used.add("openai")
    return used


def _export_api_keys_to_env(settings: LLMSettings) -> None:
    """LiteLLM читает API ключи / URL из os.environ. Прокидываем из pydantic settings.

    Экспортируем только ключи фактически используемых провайдеров (по model_aliases),
    чтобы лишние секреты не утекали в дочерние процессы.
    """
    # ВАЖНО: используем = вместо setdefault — наш settings.ollama_base_url
    # должен побеждать любой default, который мог быть в Docker-окружении.
    os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url

    try:
        used_providers = _detect_used_providers(settings.model_aliases)
    except Exception:
        # Если не получилось загрузить aliases (битый YAML и т.п.) — fallback
        # на экспорт всех ключей, чтобы не блокировать запуск.
        used_providers = set(_PROVIDER_KEY_NAMES.keys())

    mappings = (
        ("openrouter", settings.openrouter_api_key),
        ("groq", settings.groq_api_key),
        ("huggingface", settings.huggingface_api_key),
        ("anthropic", settings.anthropic_api_key),
        ("openai", settings.openai_api_key),
    )
    for provider, secret in mappings:
        if provider not in used_providers:
            continue
        env_name = _PROVIDER_KEY_NAMES[provider]
        if secret is not None and env_name not in os.environ:
            os.environ[env_name] = secret.get_secret_value()


def _is_ollama(model: str) -> bool:
    return model.startswith(_OLLAMA_PREFIXES)


def _build_provider_kwargs(
    model: str,
    response_schema: type[BaseModel],
    temperature: float,
) -> dict[str, Any]:
    """Сформировать provider-specific kwargs для litellm.acompletion.

    Ollama: native JSON Schema constrained decoding + расширенные options.
    Прочие: стандартный response_format=json_object.
    """
    if _is_ollama(model):
        # ВАЖНО: всё Ollama-специфичное (`format`, `options`, `keep_alive`) передаём
        # через `extra_body`, иначе LiteLLM оборачивает наш `options` ещё одним
        # уровнем → Ollama выдаёт WARN "invalid option provided option=options"
        # и игнорирует параметры (включая num_predict → 128 default → обрыв JSON).
        # `keep_alive=24h` — критично для производительности: без него Ollama
        # выгружает модель из VRAM между запросами (ttl=5min default), и
        # каждый запрос платит cold-start ~90 сек на GTX 1660.
        return {
            "extra_body": {
                "format": response_schema.model_json_schema(),
                "keep_alive": "24h",
                "options": {
                    "temperature": temperature,
                    "num_predict": 1024,
                    "num_ctx": 4096,
                    "top_p": 0.9,
                },
            }
        }
    return {"response_format": {"type": "json_object"}}


def _trim_history_for_retry(
    original_messages: list[dict[str, Any]],
    last_response: str,
    feedback: str,
) -> list[dict[str, Any]]:
    """Не накапливать всю историю попыток — это раздувает контекст 4–5x за пару retry.

    Оставляем: оригинальный user message + последний ассистент + новый user feedback.
    """
    return [
        *original_messages,
        {"role": "assistant", "content": last_response},
        {"role": "user", "content": feedback},
    ]


class LiteLLMProvider:
    """Реализация LLMProvider через LiteLLM.

    Маппинг alias → real model берётся из `settings.model_aliases` (configs/models.yaml).
    """

    MAX_VALIDATION_RETRIES = 2

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

        Поднимает либо `LLMNetworkError` (timeout/HTTP/connection), либо
        `LLMResponseValidationError` (JSON parse / Pydantic) — узлы могут
        обрабатывать их раздельно.
        """
        model = self.resolve_model(model_alias)
        original_messages = list(messages)
        current_messages = list(messages)
        last_validation_error: Exception | None = None

        for validation_attempt in range(self.MAX_VALIDATION_RETRIES + 1):
            content = await self._network_call_with_timeout(
                model=model,
                messages=current_messages,
                response_schema=response_schema,
                temperature=temperature,
                attempt_number=validation_attempt + 1,
            )

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
                current_messages = self._build_retry_messages(original_messages, content, e)

        raise LLMResponseValidationError(
            response_schema.__name__,
            str(last_validation_error or "unknown"),
            attempt=self.MAX_VALIDATION_RETRIES + 1,
        )

    async def _network_call_with_timeout(
        self,
        model: str,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel],
        temperature: float,
        attempt_number: int,
    ) -> str:
        """Обёртка над `_call_with_network_retry` с timeout и нормализацией исключений."""
        try:
            return await asyncio.wait_for(
                self._call_with_network_retry(
                    model=model,
                    messages=messages,
                    response_schema=response_schema,
                    temperature=temperature,
                ),
                timeout=self._settings.request_timeout_s,
            )
        except TimeoutError as e:
            _log.warning(
                "llm.network_timeout",
                schema=response_schema.__name__,
                timeout_s=self._settings.request_timeout_s,
            )
            raise LLMNetworkError(
                response_schema.__name__,
                f"timeout after {self._settings.request_timeout_s}s: {e}",
                attempt=attempt_number,
            ) from e
        except (LLMResponseValidationError, LLMBudgetExceededError):
            raise
        except Exception as e:
            _log.warning(
                "llm.network_failed",
                schema=response_schema.__name__,
                error=str(e)[:200],
            )
            hint = self._network_error_hint(model, e)
            raise LLMNetworkError(
                response_schema.__name__,
                f"{type(e).__name__}: {e}{hint}",
                attempt=attempt_number,
            ) from e

    @staticmethod
    def _build_retry_messages(
        original_messages: list[dict[str, Any]],
        last_content: str,
        validation_error: Exception,
    ) -> list[dict[str, Any]]:
        """Подготовить контекст следующей попытки после validation-ошибки."""
        feedback = (
            f"Your previous response failed schema validation: {validation_error}. "
            f"Return strictly valid JSON matching the schema. "
            f"No prose, no markdown fences, just the JSON object."
        )
        return _trim_history_for_retry(original_messages, last_content, feedback)

    async def _call_with_network_retry(
        self,
        model: str,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel],
        temperature: float,
    ) -> str:
        """Один вызов LLM с retry на 429/5xx через tenacity."""
        import litellm

        provider_kwargs = _build_provider_kwargs(model, response_schema, temperature)

        # Явно передаём api_base для Ollama — иначе LiteLLM игнорирует env
        # OLLAMA_API_BASE и использует свой default http://localhost:11434
        # (что в контейнере означает «сам контейнер», не хост и не sidecar).
        api_base_kwarg: dict[str, Any] = {}
        if _is_ollama(model):
            api_base_kwarg["api_base"] = self._settings.ollama_base_url

        async for attempt in self._retrying:
            with attempt:
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=self._settings.request_timeout_s,
                    **api_base_kwarg,
                    **provider_kwargs,
                )
                self._track_cost_and_check_budget(response, model)

                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise LLMResponseValidationError(
                        response_schema.__name__,
                        f"expected string content, got {type(content).__name__}",
                    )
                return content

        raise RuntimeError("retrying loop exited without result (should not happen)")

    def _track_cost_and_check_budget(self, response: Any, model: str) -> None:
        """Обновить накопленную стоимость и поднять `LLMBudgetExceededError` при превышении.

        Cost-tracking ошибки (например, неизвестная модель в litellm.completion_cost)
        логируются на WARN и не валят запрос — стоимость 0 USD безопаснее, чем фейл.
        """
        import litellm

        try:
            cost = litellm.completion_cost(completion_response=response)
            self._cost_total_usd += float(cost or 0.0)
            _log.info(
                "llm.completion",
                model=model,
                cost_usd=float(cost or 0.0),
                cost_total_usd=self._cost_total_usd,
            )
        except LLMBudgetExceededError:
            raise
        except Exception as e:
            _log.warning("llm.cost_tracking_failed", error=str(e))

        # Soft-budget enforcement: имеет смысл только для cloud-LLM (cost > 0).
        budget = self._settings.soft_budget_usd
        if budget > 0 and self._cost_total_usd > budget:
            _log.error(
                "llm.budget_exceeded",
                total_cost_usd=self._cost_total_usd,
                budget_usd=budget,
            )
            raise LLMBudgetExceededError(
                total_cost_usd=self._cost_total_usd,
                budget_usd=budget,
            )

    def _network_error_hint(self, model: str, error: Exception) -> str:
        """Понятная подсказка пользователю по типу network-ошибки."""
        err_str = str(error).lower()
        is_connection = (
            "connection" in err_str
            or "refused" in err_str
            or "unable to connect" in err_str
            or "name or service" in err_str
        )
        if not is_connection:
            return ""
        if _is_ollama(model):
            return (
                f"\n  >> Ollama не отвечает на {self._settings.ollama_base_url}.\n"
                f"    Запустите `ollama serve` (нативно) ИЛИ\n"
                f"    `docker compose --profile local-llm up` (через Docker).\n"
                f"    Скачать Ollama: https://ollama.com"
            )
        # cloud провайдер
        provider_hint = ""
        if model.startswith("anthropic/"):
            provider_hint = "ANTHROPIC_API_KEY"
        elif model.startswith(("openai/", "gpt-")):
            provider_hint = "OPENAI_API_KEY"
        elif model.startswith("openrouter/"):
            provider_hint = "OPENROUTER_API_KEY"
        elif model.startswith("groq/"):
            provider_hint = "GROQ_API_KEY"
        if provider_hint:
            return (
                f"\n  >> Не могу подключиться к cloud LLM. Проверьте, что выставлен "
                f"`LLM_{provider_hint}` в .env."
            )
        return ""

    @staticmethod
    def _encode_image(image: Path | bytes) -> str:
        if isinstance(image, Path):
            return base64.b64encode(image.read_bytes()).decode("ascii")
        return base64.b64encode(image).decode("ascii")
