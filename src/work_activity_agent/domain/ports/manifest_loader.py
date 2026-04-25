"""Порт ManifestLoader для чтения метаданных скриншотов из manifest.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from work_activity_agent.domain.models.screenshot import ScreenshotMetadata


class ManifestLoader(Protocol):
    """Загружает манифест с метаданными скриншотов.

    Возвращает dict[относительный_путь_файла, ScreenshotMetadata].
    """

    def load(self, manifest_path: Path) -> dict[str, ScreenshotMetadata]:
        """Прочитать manifest.yaml.

        :param manifest_path: путь к manifest.yaml
        :raises ManifestParseError: если файл невалиден
        :return: маппинг относительных путей в метаданные
        """
        ...
