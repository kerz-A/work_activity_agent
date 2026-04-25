"""Модели риска: TimeInterval, RiskFlag, TimelinePattern, RiskScore."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from work_activity_agent.domain.enums import RiskFlagType, RiskLevel
from work_activity_agent.domain.errors import InvalidTimeIntervalError


class TimeInterval(BaseModel):
    """Временной интервал [start, end). Оба конца — UTC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("interval bounds must be timezone-aware (UTC)")
        return value

    @model_validator(mode="after")
    def _check_order(self) -> TimeInterval:
        if self.end < self.start:
            raise InvalidTimeIntervalError(f"end {self.end} < start {self.start}")
        return self


class RiskFlag(BaseModel):
    """Атомарный сигнал риска по эпизоду (ТЗ §11 — risk_flags)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: RiskFlagType
    interval: TimeInterval
    severity: RiskLevel
    evidence: Annotated[str, Field(min_length=1)]
    screenshot_ids: tuple[str, ...] = Field(default_factory=tuple, min_length=1)
    requires_human_review: bool = False


class TimelinePattern(BaseModel):
    """Паттерн, обнаруженный по серии скриншотов (ТЗ §6 Timeline Pattern Agent)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_id: Annotated[str, Field(min_length=1)]
    interval: TimeInterval
    pattern: Annotated[str, Field(min_length=1)]
    risk_level: RiskLevel
    reason: Annotated[str, Field(min_length=1)]
    requires_review: bool
    screenshot_ids: tuple[str, ...] = Field(default_factory=tuple, min_length=1)


class RiskScore(BaseModel):
    """Time Farming Risk Score (ТЗ §5).

    score: 0-100 (выше = больше подозрений).
    components: вклад каждого фактора (для прозрачности и дебага).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    employee_id: Annotated[str, Field(min_length=1)]
    date: date
    score: Annotated[int, Field(ge=0, le=100)]
    level: RiskLevel
    components: dict[str, Annotated[float, Field(ge=0.0, le=1.0)]]
    summary: Annotated[str, Field(min_length=1)]
    recommended_action: Annotated[str, Field(min_length=1)]
