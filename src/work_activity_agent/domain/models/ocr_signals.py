"""OCRSignals — детерминистичные сигналы из Tesseract-вывода.

Извлекаются регулярками из OCR-текста скриншота ДО Vision-узла. Цель — снять
с слабой LLM-модели работу, которую может сделать обычный regex (определение
домена, типа страницы, типа приложения). Все поля могут быть None, если
регулярки не сработали.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

AppKind = Literal["browser", "ide", "messenger", "office", "other"]


class OCRSignals(BaseModel):
    """Структурированные сигналы из OCR-текста скрина (без участия LLM)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    raw_text: tuple[str, ...] = ()
    detected_domain: str | None = None
    domain_category: str | None = None  # "job_search" / "entertainment" / "productive_office" / ...
    detected_page_kind: str | None = None  # "vacancy_list" / "video_feed" / ...
    detected_app_kind: AppKind | None = None
    tab_titles: tuple[str, ...] = ()
