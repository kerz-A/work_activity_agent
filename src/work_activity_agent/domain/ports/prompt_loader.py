"""Порт PromptLoader и модель PromptTemplate."""

from __future__ import annotations

from typing import Annotated, Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplate(BaseModel):
    """Шаблон промпта, загруженный из файла .md с YAML frontmatter."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    model_alias: Annotated[str, Field(min_length=1)]
    response_schema_ref: str | None = None
    description: str | None = None
    content: Annotated[str, Field(min_length=1)]

    def render(self, **variables: Any) -> str:
        """Подставить переменные в шаблон через jinja2.

        Реализация делегируется в infrastructure (jinja2 — внешняя зависимость).
        Здесь — заглушка с ленивым импортом jinja2 чтобы не тащить в domain.
        """
        from jinja2 import Template  # локальный импорт, тестируется на интеграционном уровне

        return Template(self.content).render(**variables)


class PromptLoader(Protocol):
    """Загружает шаблоны промптов из файловой системы / реестра."""

    def load(self, name: str, *, version: str | None = None) -> PromptTemplate:
        """Загрузить промпт по имени.

        :param name: имя промпта (например, "vision_describe")
        :param version: конкретная версия (по умолчанию — последняя в configs/prompts/)
        :raises PromptNotFoundError: если не найден
        """
        ...
