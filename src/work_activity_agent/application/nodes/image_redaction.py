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

    def image_redaction_node(state: AgentState) -> AgentState:
        log.info(
            "image_redaction.start",
            run_id=state.run_id,
            screenshots_count=len(state.screenshots),
        )

        redacted: dict[str, RedactedScreenshot] = {}
        errors: list[NodeError] = []

        for screenshot in state.screenshots:
            output_path = screenshot.path.with_name(
                f"{screenshot.path.stem}.redacted{screenshot.path.suffix}"
            )
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
                log.warning("image_redaction.failed", screenshot_id=screenshot.id, error=str(e))
                errors.append(
                    NodeError(
                        node="image_redaction",
                        screenshot_id=screenshot.id,
                        message=str(e),
                    )
                )

        log.info("image_redaction.done", redacted_count=len(redacted), errors=len(errors))
        return state.model_copy(
            update={
                "redacted_screenshots": redacted,
                "errors": [*state.errors, *errors],
            }
        )

    return image_redaction_node
