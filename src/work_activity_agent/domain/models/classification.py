"""Модели результатов Classifier и Relevance узлов."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from work_activity_agent.domain.enums import ActivityType, RelevanceLevel, RiskFlagType
from work_activity_agent.domain.models._validators import FlexibleStringTuple


def _to_risk_flags_tuple(value: Any) -> tuple[Any, ...]:
    """str → (str,), list → tuple. Для устойчивости к json_object выходу."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


_FlexibleRiskFlagsTuple = BeforeValidator(_to_risk_flags_tuple)


class ClassificationResult(BaseModel):
    """Результат Activity Classification Agent (ТЗ §3, §22.9)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    activity_type: ActivityType
    category: str
    evidence: Annotated[tuple[str, ...], FlexibleStringTuple, Field(min_length=1, max_length=10)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class RelevanceResult(BaseModel):
    """Результат Task Relevance Agent (ТЗ §5).

    Если tracked_task is None — relevance = UNCLEAR без вызова LLM.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    tracked_task: str | None
    screenshot_activity: str
    relevance: RelevanceLevel
    risk_flags: Annotated[tuple[RiskFlagType, ...], _FlexibleRiskFlagsTuple] = ()
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    note: str | None = None
