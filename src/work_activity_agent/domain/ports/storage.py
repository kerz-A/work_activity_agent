"""Порт ScreenshotStorage для чтения/записи скриншотов."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


class ScreenshotStorage(Protocol):
    """Абстракция хранилища скриншотов (LocalFS, S3, и т.п.).

    На MVP — `LocalFSStorage`. Интерфейс под S3 — задел на будущее.
    """

    def list_screenshots(self, root: Path) -> Iterable[Path]:
        """Перечислить файлы изображений в директории (рекурсивно).

        Возвращает только файлы с расширениями .png/.jpg/.jpeg/.webp.
        """
        ...

    def read_bytes(self, path: Path) -> bytes:
        """Прочитать содержимое файла."""
        ...

    def write_redacted(self, original: Path, content: bytes) -> Path:
        """Сохранить маскированную копию рядом с оригиналом, вернуть путь."""
        ...
