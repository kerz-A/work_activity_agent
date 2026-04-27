"""Узел ImageRedaction: закрашивает PII на изображении ДО Vision (ТЗ §23)."""

from __future__ import annotations

from collections.abc import Callable

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.errors import RedactionError
from work_activity_agent.domain.models.screenshot import RedactedScreenshot
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_image_redaction_node(deps: Deps) -> Callable[[AgentState], AgentState]:
    log = get_logger("image_redaction")
    privacy_strict = deps.settings.llm.privacy_strict
    # Redacted-файлы пишем в writable директорию, НЕ рядом с оригиналом.
    # Иначе ломается на read-only input volume (Docker `-v ...:/app/fixtures:ro`).
    # Путь резолвится в Settings: явный redacted_dir → checkpoint_dir/redacted.
    redacted_dir = deps.settings.resolved_redacted_dir()
    redacted_dir.mkdir(parents=True, exist_ok=True)

    def image_redaction_node(state: AgentState) -> AgentState:
        log.info(
            "image_redaction.start",
            run_id=state.run_id,
            screenshots_count=len(state.screenshots),
            privacy_strict=privacy_strict,
            redacted_dir=str(redacted_dir),
        )

        redacted: dict[str, RedactedScreenshot] = {}
        errors: list[NodeError] = []

        for screenshot in state.screenshots:
            output_path = redacted_dir / f"{screenshot.id}.redacted{screenshot.path.suffix}"
            try:
                result = deps.image_redactor.redact(screenshot, output_path)
                redacted[screenshot.id] = result
                if result.has_pii:
                    log.info(
                        "image_redaction.pii_found",
                        screenshot_id=screenshot.id,
                        types=[t.value for t in result.detected_types],
                        bboxes=result.bboxes_count,
                    )
            except RedactionError as e:
                if privacy_strict:
                    # Strict mode: НЕ пускаем нередактированный скрин в Vision.
                    # Скрин выпадает из дальнейшего pipeline; ошибка фиксируется.
                    log.warning(
                        "image_redaction.dropped_strict",
                        screenshot_id=screenshot.id,
                        error=str(e),
                    )
                    errors.append(
                        NodeError(
                            node="image_redaction",
                            screenshot_id=screenshot.id,
                            message=f"redaction failed, dropped (privacy_strict=True): {e}",
                        )
                    )
                    continue
                # Lax mode: graceful degradation — fallback на оригинал.
                # Приватность компенсируется TextRedactor'ом после Vision на visible_text.
                log.warning(
                    "image_redaction.failed_using_original",
                    screenshot_id=screenshot.id,
                    error=str(e),
                )
                redacted[screenshot.id] = RedactedScreenshot(
                    original=screenshot,
                    redacted_path=screenshot.path,
                )
                errors.append(
                    NodeError(
                        node="image_redaction",
                        screenshot_id=screenshot.id,
                        message=f"redaction failed, using original: {e}",
                    )
                )

        if not redacted and state.screenshots:
            log.error(
                "image_redaction.all_dropped",
                screenshots_total=len(state.screenshots),
                errors=len(errors),
                privacy_strict=privacy_strict,
                hint="ALL screenshots dropped/failed. Common causes:\n"
                "  1. spaCy en_core_web_sm not installed → Presidio Analyzer fails on init\n"
                "  2. Tesseract not in PATH or missing language packs\n"
                "  3. Run `work-activity-agent doctor` for diagnostics",
            )

        log.info("image_redaction.done", redacted_count=len(redacted), errors=len(errors))
        return state.model_copy(
            update={
                "redacted_screenshots": redacted,
                "errors": [*state.errors, *errors],
            }
        )

    return image_redaction_node
