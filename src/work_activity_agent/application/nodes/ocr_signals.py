"""Узел OCRSignals: запускает Tesseract на каждый скрин и применяет
DomainClassifier для извлечения детерминистичных сигналов (домен, тип
страницы, тип приложения, заголовки вкладок).

Важно: OCR работает на **оригинальной** картинке, не на redacted-версии.
Presidio закрашивает PII прямоугольниками и при этом часто захватывает
домен/URL/заголовки вкладок (особенно url-bar) — что делает невозможным
определение домена из redacted версии. После OCR raw_text прогоняется
через text_redactor чтобы убрать email/телефоны/токены из state.

Этот узел не зависит от LLM — на скрине hh.ru detected_domain="hh.ru"
получается стабильно от прогона к прогону.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from work_activity_agent.application.services.domain_classifier import DomainClassifier
from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.models.ocr_signals import OCRSignals
from work_activity_agent.infrastructure.observability.logging import get_logger

_DEFAULT_RULES_PATH = Path("configs/domain_rules.yaml")


def make_ocr_signals_node(deps: Deps) -> Callable[[AgentState], AgentState]:
    """Фабрика узла. Сама загружает domain_rules.yaml."""
    log = get_logger("ocr_signals")
    domain_classifier = DomainClassifier.from_yaml(_DEFAULT_RULES_PATH)

    def ocr_signals_node(state: AgentState) -> AgentState:
        # OCR на оригинале (не redacted) — Presidio закрашивает URL/домен.
        # Берём screenshots в порядке collector, фильтруем по тем, что прошли
        # ImageRedaction (на случай когда privacy_strict сбросил скрин).
        kept_ids = set(state.redacted_screenshots.keys())
        input_screenshots = [s for s in state.screenshots if s.id in kept_ids]
        input_count = len(input_screenshots)
        log.info(
            "ocr_signals.start",
            run_id=state.run_id,
            screenshots_count=input_count,
        )
        if input_count == 0:
            log.warning("ocr_signals.skipped_empty_input")
            return state.model_copy(update={"ocr_signals": {}})

        signals: dict[str, OCRSignals] = {}
        errors: list[NodeError] = []

        for screenshot in input_screenshots:
            screenshot_id = screenshot.id
            try:
                raw_text = _ocr_image(screenshot.path)
            except Exception as e:  # noqa: BLE001 — не валим pipeline на одном скрине
                log.warning(
                    "ocr_signals.ocr_failed",
                    screenshot_id=screenshot_id,
                    error=str(e)[:200],
                )
                errors.append(
                    NodeError(
                        node="ocr_signals",
                        screenshot_id=screenshot_id,
                        message=f"ocr failed: {e}"[:500],
                    )
                )
                # Записываем пустой OCRSignals чтобы downstream-узлы видели наличие записи
                signals[screenshot_id] = OCRSignals(screenshot_id=screenshot_id)
                continue

            # Прогоняем raw OCR через text_redactor (regex по PII) перед
            # классификацией. Это маскирует email/phone/токены, но НЕ домены —
            # значит DomainClassifier всё равно увидит "hh.ru" и т.п.
            redacted_text, _ = deps.text_redactor.redact(raw_text)
            signal = domain_classifier.classify(screenshot_id, redacted_text)
            signals[screenshot_id] = signal
            if signal.detected_domain or signal.domain_category:
                log.info(
                    "ocr_signals.domain_detected",
                    screenshot_id=screenshot_id,
                    domain=signal.detected_domain,
                    domain_category=signal.domain_category,
                    page_kind=signal.detected_page_kind,
                    app_kind=signal.detected_app_kind,
                )

        log.info(
            "ocr_signals.done",
            total=len(signals),
            with_domain=sum(1 for s in signals.values() if s.detected_domain),
            errors=len(errors),
        )
        return state.model_copy(
            update={
                "ocr_signals": signals,
                "errors": [*state.errors, *errors],
            }
        )

    return ocr_signals_node


def _ocr_image(image_path: Path) -> tuple[str, ...]:
    """Прогон Tesseract на изображении. Возвращает кортеж непустых строк.

    Важно: используется тот же pytesseract, что и в presidio_image_redactor —
    он уже сконфигурирован и Tesseract найден в PATH (или на стандартном
    Windows-пути).
    """
    import pytesseract  # type: ignore[import-untyped]
    from PIL import Image

    # Конфигурация tesseract_cmd уже произведена при инициализации
    # PresidioImageRedactor (он вызывает _configure_tesseract). Однако если
    # PresidioImageRedactor НЕ был инстанцирован (NoopImageRedactor) — нужно
    # сделать это здесь тоже. Идемпотентно — настройка одного и того же пути
    # повторно не вредит.
    from work_activity_agent.infrastructure.redaction.presidio_image_redactor import (
        _configure_tesseract,
    )

    _configure_tesseract()

    with Image.open(image_path) as img:
        # rus+eng: на русскоязычных скринах Tesseract без -l rus отдаёт мусор.
        # Если rus traineddata не установлена, fallback на eng.
        try:
            text = pytesseract.image_to_string(img, lang="rus+eng")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(img, lang="eng")

    # Раздробить на непустые строки (для удобства downstream-обработки)
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    return lines
