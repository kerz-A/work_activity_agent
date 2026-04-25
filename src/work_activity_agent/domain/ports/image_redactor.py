"""Порт ImageRedactor — закрашивает PII прямо на изображении ДО Vision (ТЗ §23)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from work_activity_agent.domain.models.screenshot import RedactedScreenshot, Screenshot


class ImageRedactor(Protocol):
    """Закрашивает PII на изображении (используется ДО Vision).

    Основная реализация — `PresidioImageRedactor` (Tesseract + Presidio Analyzer).
    Для тестов и dry-run — `NoopImageRedactor`.
    """

    def redact(self, screenshot: Screenshot, output_path: Path) -> RedactedScreenshot:
        """Прочитать изображение, найти PII через OCR + Analyzer, закрасить bbox'ы.

        :param screenshot: оригинальный скриншот
        :param output_path: куда сохранить маскированную копию
        :return: RedactedScreenshot с информацией о найденном
        :raises RedactionError: если изображение не читается или OCR падает
        """
        ...
