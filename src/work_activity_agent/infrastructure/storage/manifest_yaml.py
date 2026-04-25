"""YamlManifestLoader — реализация ManifestLoader через YAML файл."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from work_activity_agent.domain.errors import ManifestParseError
from work_activity_agent.domain.models.screenshot import ScreenshotMetadata


class YamlManifestLoader:
    """Загружает manifest.yaml формата:

        version: 1
        screenshots:
          - file: productive/dev1_vscode_001.png
            employee_id: developer_1
            project_id: client_crm
            task_id: TASK-123
            tracked_task_title: "Fix payment retry bug"
            tracked_minutes: 10
            app_hint: "VS Code"

    Возвращает dict[относительный_путь_файла, ScreenshotMetadata].
    Поле `captured_at` намеренно не маппится сюда — оно живёт в Screenshot, не в metadata.
    """

    SUPPORTED_VERSIONS = (1,)

    def load(self, manifest_path: Path) -> dict[str, ScreenshotMetadata]:
        if not manifest_path.exists():
            raise ManifestParseError(f"manifest not found: {manifest_path}")

        try:
            with manifest_path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ManifestParseError(f"invalid YAML in {manifest_path}: {e}") from e

        if raw is None:
            return {}

        if not isinstance(raw, dict):
            raise ManifestParseError(f"manifest root must be a mapping, got {type(raw).__name__}")

        version = raw.get("version")
        if version not in self.SUPPORTED_VERSIONS:
            raise ManifestParseError(
                f"unsupported manifest version: {version!r}. Supported: {self.SUPPORTED_VERSIONS}"
            )

        entries = raw.get("screenshots", [])
        if not isinstance(entries, list):
            raise ManifestParseError(f"'screenshots' must be a list, got {type(entries).__name__}")

        result: dict[str, ScreenshotMetadata] = {}
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ManifestParseError(
                    f"entry #{idx} must be a mapping, got {type(entry).__name__}"
                )
            file_key = entry.get("file")
            if not isinstance(file_key, str) or not file_key:
                raise ManifestParseError(f"entry #{idx} missing or empty 'file' field")

            metadata_fields = self._extract_metadata_fields(entry)
            try:
                metadata = ScreenshotMetadata(**metadata_fields)
            except ValidationError as e:
                raise ManifestParseError(
                    f"entry #{idx} ({file_key}) invalid metadata: {e.errors()}"
                ) from e

            # Нормализуем разделитель путей
            normalized_key = file_key.replace("\\", "/")
            result[normalized_key] = metadata

        return result

    @staticmethod
    def _extract_metadata_fields(entry: dict[str, Any]) -> dict[str, Any]:
        """Отфильтровать только поля ScreenshotMetadata."""
        allowed = {
            "employee_id",
            "project_id",
            "task_id",
            "tracked_task_title",
            "tracked_minutes",
            "app_hint",
        }
        return {k: v for k, v in entry.items() if k in allowed}
