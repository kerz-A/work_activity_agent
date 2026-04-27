"""Узел Relevance: сравнение скриншота с tracked_task_title (ТЗ §5)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import RelevanceLevel
from work_activity_agent.domain.errors import (
    LLMBudgetExceededError,
    LLMNetworkError,
    LLMResponseValidationError,
)
from work_activity_agent.domain.models.classification import RelevanceResult
from work_activity_agent.domain.models.vision import VisionResult
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_relevance_node(deps: Deps) -> Callable[[AgentState], Awaitable[AgentState]]:
    log = get_logger("relevance")

    relevance_cfg = deps.settings.risk.relevance_config
    max_concurrent = int(relevance_cfg.get("max_concurrent", 2))
    semaphore = asyncio.Semaphore(max_concurrent)

    async def relevance_node(state: AgentState) -> AgentState:
        input_count = len(state.vision_results)
        log.info(
            "relevance.start",
            run_id=state.run_id,
            vision_results_count=input_count,
            max_concurrent=max_concurrent,
        )
        if input_count == 0:
            log.warning(
                "relevance.skipped_empty_input",
                hint="vision_results is empty",
            )
            return state.model_copy(update={"relevances": {}})

        prompt_template = deps.prompt_loader.load("task_relevance")
        screenshots_by_id = {s.id: s for s in state.screenshots}

        results: dict[str, RelevanceResult] = {}
        errors: list[NodeError] = []

        async def _evaluate(screenshot_id: str, vision: VisionResult) -> None:
            screenshot = screenshots_by_id.get(screenshot_id)
            tracked_task = screenshot.metadata.tracked_task_title if screenshot else None

            # Без задачи — relevance UNCLEAR без LLM-вызова (экономия)
            if not tracked_task:
                results[screenshot_id] = RelevanceResult(
                    screenshot_id=screenshot_id,
                    tracked_task=None,
                    screenshot_activity=vision.interpreted_activity,
                    relevance=RelevanceLevel.UNCLEAR,
                    confidence=0.5,
                    note="No tracked_task_title — relevance unclear by default",
                )
                return

            prompt = prompt_template.render(
                screenshot_id=screenshot_id,
                tracked_task=tracked_task,
                vision_json=vision.model_dump_json(),
            )
            async with semaphore:
                try:
                    result = await deps.llm.classify(
                        prompt=prompt,
                        response_schema=RelevanceResult,
                        model_alias=prompt_template.model_alias,
                    )
                    results[screenshot_id] = result
                except (LLMResponseValidationError, LLMNetworkError) as e:
                    kind = "network" if isinstance(e, LLMNetworkError) else "validation"
                    log.warning(
                        "relevance.failed",
                        screenshot_id=screenshot_id,
                        kind=kind,
                        error=str(e)[:200],
                    )
                    errors.append(
                        NodeError(
                            node="relevance",
                            screenshot_id=screenshot_id,
                            message=f"{kind}: {e}"[:500],
                        )
                    )

        try:
            await asyncio.gather(*(_evaluate(sid, vr) for sid, vr in state.vision_results.items()))
        except LLMBudgetExceededError as e:
            log.error(
                "relevance.budget_exceeded",
                processed=len(results),
                total=len(state.vision_results),
                error=str(e),
            )
            errors.append(
                NodeError(node="relevance", screenshot_id=None, message=f"budget_exceeded: {e}")
            )

        log.info("relevance.done", success=len(results), errors=len(errors))
        return state.model_copy(
            update={
                "relevances": results,
                "errors": [*state.errors, *errors],
            }
        )

    return relevance_node
