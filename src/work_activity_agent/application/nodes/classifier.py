"""Узел Classifier: классификация скриншотов по 11 категориям активности (ТЗ §3).

Особенности устойчивости к малым LLM (Gemma 3 4B):
- семафор concurrency, чтобы локальная Ollama не упиралась в VRAM/timeout;
- raздельная обработка `LLMNetworkError` и `LLMResponseValidationError` —
  для метрик и анализа;
- fallback на `NEUTRAL_UNCLEAR` после исчерпания retry, чтобы скрин
  не выпадал из RiskCalculator (знаменатель должен оставаться корректным).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import ActivityType
from work_activity_agent.domain.errors import (
    LLMBudgetExceededError,
    LLMNetworkError,
    LLMResponseValidationError,
)
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.ocr_signals import OCRSignals
from work_activity_agent.infrastructure.observability.logging import get_logger

# Detrministic override map: ocr_signals.domain_category → activity_type.
# Применяется ПОСЛЕ ответа LLM. Слабые модели (Gemma 3 4B) систематически
# игнорируют hard-правила в промпте и возвращают productive_work для всего.
# Этот rescue-слой компенсирует баг LLM — категория, обнаруженная regex'ами
# по OCR-тексту, доверительнее, чем ответ слабой vision/classifier-модели.
_OCR_OVERRIDE_MAP: dict[str, ActivityType] = {
    "job_search": ActivityType.JOB_SEARCH_SIGNAL,
    "entertainment": ActivityType.NON_WORK,
    "personal_messaging": ActivityType.SENSITIVE_PRIVATE,
}


def make_classifier_node(deps: Deps) -> Callable[[AgentState], Awaitable[AgentState]]:
    log = get_logger("classifier")

    classifier_cfg = deps.settings.risk.classifier_config
    max_concurrent = int(classifier_cfg.get("max_concurrent", 2))
    semaphore = asyncio.Semaphore(max_concurrent)

    async def classifier_node(state: AgentState) -> AgentState:
        input_count = len(state.vision_results)
        log.info(
            "classifier.start",
            run_id=state.run_id,
            vision_results_count=input_count,
            max_concurrent=max_concurrent,
        )
        if input_count == 0:
            log.warning(
                "classifier.skipped_empty_input",
                hint="vision_results is empty — Vision didn't produce results",
            )
            return state.model_copy(update={"classifications": {}})

        prompt_template = deps.prompt_loader.load("classify_activity")

        # Индекс по screenshot_id → метаданные. Нужен Classifier-у, чтобы
        # подмешать tracked_task_title в промпт.
        screenshots_by_id = {s.id: s for s in state.screenshots}

        results: dict[str, ClassificationResult] = {}
        errors: list[NodeError] = []

        async def _classify(screenshot_id: str, vision_payload: str) -> None:
            screenshot = screenshots_by_id.get(screenshot_id)
            tracked_task = (
                screenshot.metadata.tracked_task_title if screenshot is not None else None
            )
            ocr = state.ocr_signals.get(screenshot_id)
            prompt = prompt_template.render(
                screenshot_id=screenshot_id,
                vision_json=vision_payload,
                tracked_task=tracked_task,
                ocr_domain=ocr.detected_domain if ocr else None,
                ocr_domain_category=ocr.domain_category if ocr else None,
                ocr_page_kind=ocr.detected_page_kind if ocr else None,
                ocr_app_kind=ocr.detected_app_kind if ocr else None,
                ocr_tab_titles=list(ocr.tab_titles) if ocr else [],
            )
            async with semaphore:
                try:
                    result = await deps.llm.classify(
                        prompt=prompt,
                        response_schema=ClassificationResult,
                        model_alias=prompt_template.model_alias,
                    )
                    # Rescue rule: если OCR детерминистично определил категорию
                    # из risk-set — переписываем ответ LLM. Слабые модели
                    # (Gemma 4B) систематически игнорируют hard-правила.
                    results[screenshot_id] = _apply_ocr_override(result, ocr, log)
                    return
                except LLMNetworkError as e:
                    log.warning(
                        "classifier.network_failed",
                        screenshot_id=screenshot_id,
                        error=str(e)[:200],
                    )
                    error_kind = "network"
                    error_message = f"network: {e}"
                except LLMResponseValidationError as e:
                    log.warning(
                        "classifier.validation_failed",
                        screenshot_id=screenshot_id,
                        error=str(e)[:200],
                    )
                    error_kind = "validation"
                    error_message = f"validation: {e}"
                except LLMBudgetExceededError:
                    # Бюджет — глобальный сигнал стопа, поднимаем наружу gather.
                    raise
                except Exception as e:
                    # Defensive: любая другая ошибка не должна валить весь gather
                    # и терять уже посчитанные классификации других скринов.
                    log.exception(
                        "classifier.unexpected_error",
                        screenshot_id=screenshot_id,
                        error_type=type(e).__name__,
                        error=str(e)[:200],
                    )
                    error_kind = "unexpected"
                    error_message = f"unexpected:{type(e).__name__}: {e}"

            # Fallback: не теряем скрин — записываем NEUTRAL_UNCLEAR, чтобы
            # знаменатель в RiskCalculator оставался корректным. Ошибку всё
            # равно фиксируем в state.errors для отчёта менеджеру.
            results[screenshot_id] = _fallback_result(screenshot_id, error_kind)
            errors.append(
                NodeError(
                    node="classifier",
                    screenshot_id=screenshot_id,
                    message=error_message[:500],
                )
            )

        try:
            await asyncio.gather(
                *(_classify(sid, vr.model_dump_json()) for sid, vr in state.vision_results.items())
            )
        except LLMBudgetExceededError as e:
            log.error(
                "classifier.budget_exceeded",
                processed=len(results),
                total=len(state.vision_results),
                error=str(e),
            )
            errors.append(
                NodeError(node="classifier", screenshot_id=None, message=f"budget_exceeded: {e}")
            )

        log.info(
            "classifier.done",
            success=len(results) - len(errors),
            errors=len(errors),
            fallback_used=len(errors),
        )
        return state.model_copy(
            update={
                "classifications": results,
                "errors": [*state.errors, *errors],
            }
        )

    return classifier_node


def _fallback_result(screenshot_id: str, error_kind: str) -> ClassificationResult:
    """Дефолтный результат при исчерпании retry — не теряем скрин."""
    return ClassificationResult(
        screenshot_id=screenshot_id,
        activity_type=ActivityType.NEUTRAL_UNCLEAR,
        category="classification_failed",
        evidence=(f"classification_failed:{error_kind}",),
        confidence=0.0,
    )


def _apply_ocr_override(
    llm_result: ClassificationResult,
    ocr: OCRSignals | None,
    log: object,
) -> ClassificationResult:
    """Если ocr_signals детерминистично детектил категорию из risk-set —
    перезаписываем ответ LLM. Это компенсация известного бага слабых моделей,
    которые систематически возвращают productive_work несмотря на hard-правила
    в промпте.
    """
    if ocr is None or ocr.domain_category is None:
        return llm_result

    override_activity = _OCR_OVERRIDE_MAP.get(ocr.domain_category)
    if override_activity is None or llm_result.activity_type == override_activity:
        return llm_result

    # Логируем override — менеджер должен видеть, что ответ LLM был перебит OCR-сигналом.
    if hasattr(log, "info"):
        log.info(  # type: ignore[attr-defined]
            "classifier.ocr_override",
            screenshot_id=llm_result.screenshot_id,
            llm_activity=llm_result.activity_type.value,
            override_to=override_activity.value,
            ocr_domain=ocr.detected_domain,
            ocr_category=ocr.domain_category,
        )

    override_evidence = (
        f"OCR override: detected_domain={ocr.detected_domain or 'unknown'}, "
        f"category={ocr.domain_category} (LLM said {llm_result.activity_type.value})",
        *llm_result.evidence,
    )
    return llm_result.model_copy(
        update={
            "activity_type": override_activity,
            "category": ocr.domain_category,
            "evidence": override_evidence[:10],  # max 10 по схеме
        }
    )
