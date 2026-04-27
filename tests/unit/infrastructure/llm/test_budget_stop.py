"""Тесты soft_budget_usd → LLMBudgetExceededError."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from work_activity_agent.config.settings import LLMSettings
from work_activity_agent.domain.errors import LLMBudgetExceededError
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.infrastructure.llm.litellm_provider import LiteLLMProvider


@pytest.fixture
def settings_low_budget(tmp_path: Any) -> LLMSettings:
    return LLMSettings(
        soft_budget_usd=0.5,
        request_timeout_s=10,
        models_config_path=tmp_path / "noexist.yaml",
    )


def _make_response(content: str) -> Any:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_budget_exceeded_raises_after_threshold(
    settings_low_budget: LLMSettings,
) -> None:
    """Если cost накопит >budget — следующий вызов поднимает LLMBudgetExceededError."""
    provider = LiteLLMProvider(settings_low_budget)

    valid_json = '{"screenshot_id":"s1","activity_type":"productive_work","category":"x","evidence":["e"],"confidence":0.9}'
    response = _make_response(valid_json)

    with (
        patch("litellm.acompletion", return_value=response),
        patch("litellm.completion_cost", return_value=1.0),  # больше budget=0.5
        pytest.raises(LLMBudgetExceededError) as exc_info,
    ):
        await provider.classify(prompt="test", response_schema=ClassificationResult)

    assert exc_info.value.budget_usd == 0.5
    assert exc_info.value.total_cost_usd >= 0.5


@pytest.mark.asyncio
async def test_within_budget_does_not_raise(settings_low_budget: LLMSettings) -> None:
    """Если cost < budget — вызов завершается нормально."""
    provider = LiteLLMProvider(settings_low_budget)

    valid_json = '{"screenshot_id":"s1","activity_type":"productive_work","category":"x","evidence":["e"],"confidence":0.9}'
    response = _make_response(valid_json)

    with (
        patch("litellm.acompletion", return_value=response),
        patch("litellm.completion_cost", return_value=0.1),  # меньше budget
    ):
        result = await provider.classify(
            prompt="test", response_schema=ClassificationResult
        )

    assert result.screenshot_id == "s1"
    assert provider.cost_total_usd == pytest.approx(0.1)
