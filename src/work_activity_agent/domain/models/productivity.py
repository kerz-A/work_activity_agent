"""Модели Work Activity Score (ТЗ §14)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from work_activity_agent.domain.enums import WorkActivityLevel


class ActivityComponents(BaseModel):
    """Вклад компонентов Work Activity Score (ТЗ §14).

    Все значения нормализованы в [0, 1] до взвешивания.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_alignment: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    result_evidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    productive_tools_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    screen_dynamics: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    project_communication_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    work_regularity: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    no_risk_flags: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class WorkActivityScore(BaseModel):
    """Индекс продуктивности по сотруднику и дню (ТЗ §14).

    score: 0-100 (выше = более продуктивный день).
    note: явная пометка если result_evidence недоступен (нет Git/Jira).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_id: Annotated[str, Field(min_length=1)]
    date: date
    score: Annotated[int, Field(ge=0, le=100)]
    level: WorkActivityLevel
    components: ActivityComponents
    note: str | None = None
