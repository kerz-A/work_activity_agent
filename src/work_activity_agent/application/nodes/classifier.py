"""Узел Classifier: классификация скриншотов по 11 категориям активности (ТЗ §3)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.errors import LLMResponseValidationError
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_classifier_node(deps: Deps) -> Callable[[AgentState], Awaitable[AgentState]]:
    log = get_logger("classifier")

    async def classifier_node(state: AgentState) -> AgentState:
        log.info(
            "classifier.start",
            run_id=state.run_id,
            vision_results_count=len(state.vision_results),
        )

        prompt_template = deps.prompt_loader.load("classify_activity")

        results: dict[str, ClassificationResult] = {}
        errors: list[NodeError] = []

        async def _classify(screenshot_id: str, vision_payload: str) -> None:
            prompt = prompt_template.render(
                screenshot_id=screenshot_id,
                vision_json=vision_payload,
            )
            try:
                result = await deps.llm.classify(
                    prompt=prompt,
                    response_schema=ClassificationResult,
                    model_alias=prompt_template.model_alias,
                )
                results[screenshot_id] = result
            except LLMResponseValidationError as e:
                errors.append(
                    NodeError(
                        node="classifier",
                        screenshot_id=screenshot_id,
                        message=str(e)[:500],
                    )
                )

        await asyncio.gather(
            *(_classify(sid, vr.model_dump_json()) for sid, vr in state.vision_results.items())
        )

        log.info("classifier.done", success=len(results), errors=len(errors))
        return state.model_copy(
            update={
                "classifications": results,
                "errors": [*state.errors, *errors],
            }
        )

    return classifier_node
