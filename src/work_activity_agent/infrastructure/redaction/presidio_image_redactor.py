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

# Имя spaCy NLP-модели, которую мы предустанавливаем (Dockerfile + локально через uv).
# Presidio Analyzer по умолчанию ищет `en_core_web_lg` (~500 MB) и при отсутствии пытается
# скачать через pip — что в Docker (без pip в venv) даёт "No package installer found".
# Мы явно конфигурируем Presidio на лёгкую `en_core_web_sm`.
_SPACY_MODEL = "en_core_web_sm"


def _build_analyzer() -> Any:
    """Создать AnalyzerEngine с кастомным NlpEngine на en_core_web_sm (не lg).

    Ленивая инициализация — тяжёлые spaCy-модели грузятся только при первом вызове.
    """
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": _SPACY_MODEL}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


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
                from presidio_image_redactor import ImageAnalyzerEngine, ImageRedactorEngine
            except ImportError as e:
                raise RedactionError(
                    "presidio-image-redactor not installed. Run: uv sync --all-extras --dev"
                ) from e
            try:
                analyzer = _build_analyzer()
                image_analyzer = ImageAnalyzerEngine(analyzer_engine=analyzer)
                self._redactor = ImageRedactorEngine(image_analyzer_engine=image_analyzer)
            except Exception as e:
                raise RedactionError(
                    f"failed to initialize Presidio with spaCy model {_SPACY_MODEL!r}: {e}. "
                    f"Install model: uv pip install "
                    f"https://github.com/explosion/spacy-models/releases/download/"
                    f"{_SPACY_MODEL}-3.8.0/{_SPACY_MODEL}-3.8.0-py3-none-any.whl"
                ) from e
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

        # Конвертируем в RGB: Presidio может вернуть RGBA или другой mode,
        # а Ollama vision encoder принимает только RGB ("image: unknown format" иначе).
        if redacted_img.mode != "RGB":
            redacted_img = redacted_img.convert("RGB")

        # Downscale до 1024 px по большей стороне.
        # Vision-модели (Gemma 3 4B, Claude Haiku, GPT-4o-mini) эффективны при таком
        # разрешении — больше = только медленнее без выигрыша точности.
        # На GPU 6GB Gemma 3 крупные изображения дают timeout.
        max_dim = 1024
        if max(redacted_img.size) > max_dim:
            redacted_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        redacted_img.save(output_path, format="PNG")

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
            from presidio_image_redactor import ImageAnalyzerEngine
        except ImportError:
            return (), 0

        try:
            # Используем тот же кастомный analyzer (en_core_web_sm), что и в _ensure_redactor
            ocr_analyzer = ImageAnalyzerEngine(analyzer_engine=_build_analyzer())
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
