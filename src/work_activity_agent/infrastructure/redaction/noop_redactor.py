"""No-op redactors для тестов и dry-run.

ImageRedactor: копирует файл без изменений.
TextRedactor: возвращает текст как есть.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from work_activity_agent.domain.enums import SensitiveDataType
from work_activity_agent.domain.errors import RedactionError
from work_activity_agent.domain.models.screenshot import RedactedScreenshot, Screenshot


class NoopImageRedactor:
    """Копирует изображение без изменений. Для dry-run и тестов."""

    def redact(self, screenshot: Screenshot, output_path: Path) -> RedactedScreenshot:
        if not screenshot.path.exists():
            raise RedactionError(f"source image not found: {screenshot.path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(screenshot.path, output_path)
        return RedactedScreenshot(original=screenshot, redacted_path=output_path)


class NoopTextRedactor:
    """Возвращает текст как есть. Для dry-run."""

    def redact(self, texts: Sequence[str]) -> tuple[tuple[str, ...], tuple[SensitiveDataType, ...]]:
        return tuple(texts), ()
