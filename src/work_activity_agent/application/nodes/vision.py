"""Узел Vision: оцифровка скриншотов через LLM Vision."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.errors import (
    LLMBudgetExceededError,
    LLMNetworkError,
    LLMResponseValidationError,
)
from work_activity_agent.domain.models.screenshot import RedactedScreenshot
from work_activity_agent.domain.models.vision import VisionResult
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_vision_node(deps: Deps) -> Callable[[AgentState], Awaitable[AgentState]]:
    log = get_logger("vision")
    semaphore = asyncio.Semaphore(deps.settings.llm.max_concurrent_vision)

    async def vision_node(state: AgentState) -> AgentState:
        input_count = len(state.redacted_screenshots)
        log.info(
            "vision.start",
            run_id=state.run_id,
            screenshots_count=input_count,
        )
        if input_count == 0:
            log.warning(
                "vision.skipped_empty_input",
                hint="redacted_screenshots is empty — check image_redaction node "
                "(privacy_strict drops on RedactionError; verify Tesseract + spaCy)",
            )
            return state.model_copy(update={"vision_results": {}})

        prompt_template = deps.prompt_loader.load("vision_describe")

        results: dict[str, VisionResult] = {}
        errors: list[NodeError] = []

        async def _process(redacted: RedactedScreenshot) -> None:
            screenshot_id = redacted.original.id
            async with semaphore:
                prompt = prompt_template.render(
                    screenshot_id=screenshot_id,
                    has_pii_masks=redacted.has_pii,
                )
                try:
                    result = await deps.llm.vision_analyze(
                        image=redacted.redacted_path,
                        prompt=prompt,
                        response_schema=VisionResult,
                        model_alias=prompt_template.model_alias,
                    )
                    # Защитный слой: ещё раз пройдём text redactor по visible_text
                    masked_texts, _ = deps.text_redactor.redact(result.visible_text)
                    results[screenshot_id] = result.model_copy(
                        update={"visible_text": masked_texts}
                    )
                except (LLMResponseValidationError, LLMNetworkError) as e:
                    kind = "network" if isinstance(e, LLMNetworkError) else "validation"
                    log.warning(
                        "vision.failed",
                        screenshot_id=screenshot_id,
                        kind=kind,
                        error=str(e)[:200],
                    )
                    errors.append(
                        NodeError(
                            node="vision",
                            screenshot_id=screenshot_id,
                            message=f"{kind}: {e}"[:500],
                        )
                    )

        try:
            await asyncio.gather(
                *(_process(r) for r in state.redacted_screenshots.values()),
                return_exceptions=False,
            )
        except LLMBudgetExceededError as e:
            # Бюджет превышен в середине Vision — отдаём partial state.
            # Дальше Classifier/Relevance/Timeline/Reports отработают на том что успели.
            log.error(
                "vision.budget_exceeded",
                processed=len(results),
                total=len(state.redacted_screenshots),
                error=str(e),
            )
            errors.append(
                NodeError(node="vision", screenshot_id=None, message=f"budget_exceeded: {e}")
            )

        log.info("vision.done", success=len(results), errors=len(errors))
        return state.model_copy(
            update={
                "vision_results": results,
                "errors": [*state.errors, *errors],
            }
        )

    return vision_node
