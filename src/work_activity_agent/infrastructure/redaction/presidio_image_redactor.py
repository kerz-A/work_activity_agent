"""PresidioImageRedactor — закрашивает PII на изображении через Presidio Image Redactor.

Под капотом: Tesseract OCR находит текст, Presidio Analyzer ищет PII,
Presidio Image Redactor рисует чёрные прямоугольники на bbox'ах.

Используется ДО Vision-узла (приватность по ТЗ §23).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from work_activity_agent.domain.enums import SensitiveDataType
from work_activity_agent.domain.errors import RedactionError
from work_activity_agent.domain.models.screenshot import RedactedScreenshot, Screenshot

# Стандартные места установки Tesseract на Windows.
# UB-Mannheim installer ставит в "Program Files".
_WINDOWS_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")),
)


def _autodetect_tesseract() -> Path | None:
    """Найти tesseract.exe: сначала через PATH, потом стандартные места установки."""
    if (cmd := shutil.which("tesseract")) is not None:
        return Path(cmd)
    for candidate in _WINDOWS_TESSERACT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _configure_tesseract() -> None:
    """Прокинуть путь к tesseract в pytesseract если его нет в PATH."""
    try:
        import pytesseract  # type: ignore[import-untyped]
    except ImportError:
        return  # презумпция — может вообще не нужен (без Presidio)
    detected = _autodetect_tesseract()
    if detected is not None:
        pytesseract.pytesseract.tesseract_cmd = str(detected)

# Presidio entity → наш SensitiveDataType
_ENTITY_MAPPING: dict[str, SensitiveDataType] = {
    "EMAIL_ADDRESS": SensitiveDataType.EMAIL,
    "PHONE_NUMBER": SensitiveDataType.PHONE,
    "CREDIT_CARD": SensitiveDataType.BANK_DETAILS,
    "IBAN_CODE": SensitiveDataType.BANK_DETAILS,
    "US_PASSPORT": SensitiveDataType.PASSPORT,
    "US_SSN": SensitiveDataType.PASSPORT,
    "MEDICAL_LICENSE": SensitiveDataType.MEDICAL,
    "PERSON": SensitiveDataType.THIRD_PARTY,
}


class PresidioImageRedactor:
    """Реализация ImageRedactor через presidio-image-redactor.

    Lazy-инициализация: тяжёлые зависимости (Tesseract, spaCy) грузятся при первом вызове,
    не при импорте.
    """

    def __init__(self) -> None:
        self._redactor: Any | None = None

    def _ensure_redactor(self) -> Any:
        if self._redactor is None:
            _configure_tesseract()
            try:
                from presidio_image_redactor import ImageRedactorEngine
            except ImportError as e:
                raise RedactionError(
                    "presidio-image-redactor not installed. Run: uv sync --all-extras --dev"
                ) from e
            self._redactor = ImageRedactorEngine()
        return self._redactor

    def redact(self, screenshot: Screenshot, output_path: Path) -> RedactedScreenshot:
        if not screenshot.path.exists():
            raise RedactionError(f"source image not found: {screenshot.path}")

        try:
            from PIL import Image
        except ImportError as e:
            raise RedactionError("Pillow not installed") from e

        engine = self._ensure_redactor()

        try:
            with Image.open(screenshot.path) as img:
                redacted_img = engine.redact(img, fill=(0, 0, 0))
        except Exception as e:
            raise RedactionError(f"redaction failed for {screenshot.path}: {e}") from e

        output_path.parent.mkdir(parents=True, exist_ok=True)
        redacted_img.save(output_path)

        # Presidio Image Redactor не возвращает напрямую список найденных entities.
        # Обходное решение: запустить analyzer отдельно через OCR результаты для метаданных.
        detected_types, bboxes_count = self._analyze_metadata(screenshot.path)

        return RedactedScreenshot(
            original=screenshot,
            redacted_path=output_path,
            detected_types=detected_types,
            bboxes_count=bboxes_count,
        )

    def _analyze_metadata(self, image_path: Path) -> tuple[tuple[SensitiveDataType, ...], int]:
        """Прогнать OCR + Analyzer отдельно чтобы узнать какие типы PII найдены и сколько."""
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_image_redactor import ImageAnalyzerEngine
        except ImportError:
            return (), 0

        try:
            ocr_analyzer = ImageAnalyzerEngine(analyzer_engine=AnalyzerEngine())
            with __import__("PIL.Image", fromlist=["Image"]).open(image_path) as img:
                analyzer_results = ocr_analyzer.analyze(image=img, language="en")
        except Exception:
            return (), 0

        types: set[SensitiveDataType] = set()
        for r in analyzer_results:
            entity = getattr(r, "entity_type", None)
            if entity and entity in _ENTITY_MAPPING:
                types.add(_ENTITY_MAPPING[entity])

        return tuple(sorted(types, key=lambda t: t.value)), len(analyzer_results)
