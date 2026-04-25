"""LocalFSStorage — реализация ScreenshotStorage поверх локальной файловой системы."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from work_activity_agent.domain.errors import StorageError

SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})


class LocalFSStorage:
    """Чтение скриншотов из локальной директории, запись маскированных копий рядом."""

    def list_screenshots(self, root: Path) -> Iterable[Path]:
        if not root.exists():
            raise StorageError(f"input directory does not exist: {root}")
        if not root.is_dir():
            raise StorageError(f"not a directory: {root}")

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            # Исключаем результаты прошлых redaction прогонов
            if ".redacted" in path.stem:
                continue
            yield path

    def read_bytes(self, path: Path) -> bytes:
        if not path.exists():
            raise StorageError(f"file not found: {path}")
        return path.read_bytes()

    def write_redacted(self, original: Path, content: bytes) -> Path:
        """Сохранить маскированную копию рядом с оригиналом: name.redacted.png."""
        out_path = original.with_name(f"{original.stem}.redacted{original.suffix}")
        out_path.write_bytes(content)
        return out_path
