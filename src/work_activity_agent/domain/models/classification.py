"""Модели результатов Classifier и Relevance узлов."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from work_activity_agent.domain.enums import ActivityType, RelevanceLevel, RiskFlagType


class ClassificationResult(BaseModel):
    """Результат Activity Classification Agent (ТЗ §3, §22.9)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    activity_type: ActivityType
    category: str
    evidence: tuple[str, ...] = Field(default_factory=tuple, min_length=1, max_length=10)
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
    risk_flags: tuple[RiskFlagType, ...] = ()
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    note: str | None = None
