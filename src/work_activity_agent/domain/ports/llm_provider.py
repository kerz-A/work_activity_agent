"""Порт LLM-провайдера. Единственная точка интеграции с внешними LLM."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Абстракция над LLM провайдерами (Anthropic, OpenAI, локальные).

    Реализация — `infrastructure.llm.litellm_provider.LiteLLMProvider`.
    Для тестов — `infrastructure.llm.fake_provider.FakeLLMProvider`.
    """

    async def vision_analyze(
        self,
        image: Path | bytes,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "vision_primary",
        temperature: float = 0.0,
    ) -> T:
        """Vision-анализ скриншота.

        :param image: путь к файлу или bytes изображения
        :param prompt: промпт (рендеренный из шаблона)
        :param response_schema: Pydantic-модель для structured output
        :param model_alias: алиас из configs/models.yaml
        :param temperature: 0.0 для детерминизма
        :raises LLMResponseValidationError: если ответ не парсится в схему после retry
        """
        ...

    async def classify(
        self,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "text_primary",
        temperature: float = 0.0,
    ) -> T:
        """Текстовая классификация / интерпретация. Без изображения."""
        ...

    async def embed(
        self,
        text: str,
        *,
        model_alias: str = "embed_primary",
    ) -> list[float]:
        """Embeddings для семантического поиска (опц., для будущих фич)."""
        ...
