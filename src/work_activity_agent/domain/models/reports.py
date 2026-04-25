"""Модели отчётов: дневной по сотруднику, проектный, screenshot table (ТЗ §11, §12, §15)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from work_activity_agent.domain.enums import ActivityType, RelevanceLevel, RiskLevel
from work_activity_agent.domain.models.productivity import WorkActivityScore
from work_activity_agent.domain.models.risk import RiskFlag, RiskScore


class ActivityBreakdown(BaseModel):
    """Распределение времени по категориям активности (ТЗ §11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    productive_work: timedelta = timedelta(0)
    project_communication: timedelta = timedelta(0)
    research: timedelta = timedelta(0)
    admin_work: timedelta = timedelta(0)
    neutral_unclear: timedelta = timedelta(0)
    idle_static: timedelta = timedelta(0)
    non_work: timedelta = timedelta(0)
    job_search_signal: timedelta = timedelta(0)
    other_project_signal: timedelta = timedelta(0)
    sensitive_private: timedelta = timedelta(0)
    needs_human_review: timedelta = timedelta(0)

    @property
    def total(self) -> timedelta:
        return (
            self.productive_work
            + self.project_communication
            + self.research
            + self.admin_work
            + self.neutral_unclear
            + self.idle_static
            + self.non_work
            + self.job_search_signal
            + self.other_project_signal
            + self.sensitive_private
            + self.needs_human_review
        )


class EvidenceLink(BaseModel):
    """Ссылка на конкретный скриншот как доказательство (ТЗ §16: ссылки на скрины)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    screenshot_id: Annotated[str, Field(min_length=1)]
    path: Path
    caption: Annotated[str, Field(min_length=1)]


class ScreenshotTableRow(BaseModel):
    """Строка таблицы из ТЗ §15.

    | Time | Employee | Task | Summary | Activity | Relevance | Flags | Risk | Review |
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    time: str  # HH:MM формата для отображения
    employee: str
    task: str
    summary: str
    activity: ActivityType
    relevance: RelevanceLevel
    flags: tuple[str, ...] = ()
    risk: RiskLevel
    review: bool


class EmployeeReport(BaseModel):
    """Дневной отчёт по сотруднику (ТЗ §11)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_id: Annotated[str, Field(min_length=1)]
    date: date
    screenshots_total: Annotated[int, Field(ge=0)]
    tracked_time: timedelta
    breakdown: ActivityBreakdown
    risk_flags: tuple[RiskFlag, ...] = ()
    risk_score: RiskScore
    work_activity_score: WorkActivityScore
    manager_summary: Annotated[str, Field(min_length=1)]
    evidence_links: tuple[EvidenceLink, ...] = ()


class ProjectReport(BaseModel):
    """Проектный отчёт за период (ТЗ §12)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: Annotated[str, Field(min_length=1)]
    period_start: date
    period_end: date
    team_members: Annotated[int, Field(ge=0)]
    screenshots_analyzed: Annotated[int, Field(ge=0)]
    productive_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    unclear_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    non_work_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    top_tools: tuple[str, ...] = ()
    project_risks: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
