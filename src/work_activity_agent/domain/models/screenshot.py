"""Модели скриншота и его метаданных."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from work_activity_agent.domain.enums import SensitiveDataType


class ScreenshotMetadata(BaseModel):
    """Метаданные скриншота из manifest.yaml.

    Все поля опциональны — если manifest пуст или скриншот в нём отсутствует,
    метаданные остаются None и попадают в обработку как unclear.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    tracked_task_title: str | None = None
    tracked_minutes: Annotated[int, Field(ge=0)] | None = None
    app_hint: str | None = None


class Screenshot(BaseModel):
    """Сырой скриншот на входе пайплайна."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(min_length=1)]
    path: Path
    captured_at: datetime
    metadata: ScreenshotMetadata = ScreenshotMetadata()

    @field_validator("captured_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware (use UTC)")
        return value


class RedactedScreenshot(BaseModel):
    """Скриншот после прохождения ImageRedaction.

    Содержит ссылку на маскированное изображение и информацию о том, что было найдено.
    Используется как вход для Vision-узла.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original: Screenshot
    redacted_path: Path
    detected_types: tuple[SensitiveDataType, ...] = ()
    bboxes_count: Annotated[int, Field(ge=0)] = 0

    @property
    def has_pii(self) -> bool:
        return self.bboxes_count > 0
