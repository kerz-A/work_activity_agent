"""Модели результатов Vision и Redaction."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from work_activity_agent.domain.enums import RedactionAction, SensitiveDataType


class ExtractedMetadata(BaseModel):
    """Метаданные, которые Vision вытащил из самого скриншота.

    Используется как fallback если manifest.yaml не содержит данных по скриншоту
    или для перекрёстной проверки (например, Vision видит другую задачу в трекере).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_hint: str | None = None
    task_hint: str | None = None
    project_hint: str | None = None
    timestamp_hint: datetime | None = None


class VisionResult(BaseModel):
    """Структурированный результат Vision-анализа скриншота (ТЗ §2 пример)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    visible_application: str
    visible_site: str | None = None
    visible_page_type: str | None = None
    visible_text: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    interpreted_activity: str
    extracted_metadata: ExtractedMetadata = ExtractedMetadata()
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    model_used: str


class RedactionResult(BaseModel):
    """Результат работы redactor'а (image или text).

    Для image: detected_types по результатам OCR + Presidio Analyzer.
    Для text: detected_types по результатам regex/Presidio на массиве строк.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    screenshot_id: Annotated[str, Field(min_length=1)]
    detected_types: tuple[SensitiveDataType, ...] = ()
    action: RedactionAction = RedactionAction.MASK_BEFORE_REPORT
    redacted_image_path: Path | None = None
    redacted_text: tuple[str, ...] = ()

    @property
    def has_findings(self) -> bool:
        return len(self.detected_types) > 0
