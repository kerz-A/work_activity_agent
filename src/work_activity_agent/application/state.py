"""AgentState — единый pydantic-стейт для LangGraph.

Накопительная структура: каждый узел добавляет результаты в свои поля.
Зависимости (Deps) НЕ хранятся в стейте — они инжектятся в фабрики узлов.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.productivity import WorkActivityScore
from work_activity_agent.domain.models.reports import (
    EmployeeReport,
    ProjectReport,
    ScreenshotTableRow,
)
from work_activity_agent.domain.models.risk import RiskScore, TimelinePattern
from work_activity_agent.domain.models.screenshot import (
    RedactedScreenshot,
    Screenshot,
)
from work_activity_agent.domain.models.vision import VisionResult


class NodeError(BaseModel):
    """Неблокирующая ошибка узла (логгируется, граф продолжается)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: str
    screenshot_id: str | None
    message: Annotated[str, Field(min_length=1)]


class AgentState(BaseModel):
    """Стейт LangGraph. Иммутабелен — узлы возвращают обновлённую копию."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # Вход
    input_dir: Path
    employee_filter: str | None = None
    date_filter: date | None = None
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])

    # Промежуточные результаты (накапливаются по ходу графа)
    screenshots: list[Screenshot] = Field(default_factory=list)
    redacted_screenshots: dict[str, RedactedScreenshot] = Field(default_factory=dict)
    vision_results: dict[str, VisionResult] = Field(default_factory=dict)
    classifications: dict[str, ClassificationResult] = Field(default_factory=dict)
    relevances: dict[str, RelevanceResult] = Field(default_factory=dict)
    timeline_patterns: list[TimelinePattern] = Field(default_factory=list)
    risk_scores: dict[str, RiskScore] = Field(default_factory=dict)  # by employee_id
    work_activity_scores: dict[str, WorkActivityScore] = Field(default_factory=dict)

    # Финальные отчёты
    employee_reports: list[EmployeeReport] = Field(default_factory=list)
    project_reports: list[ProjectReport] = Field(default_factory=list)
    screenshot_table: list[ScreenshotTableRow] = Field(default_factory=list)

    # Ошибки узлов (не блокирующие)
    errors: list[NodeError] = Field(default_factory=list)
