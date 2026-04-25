"""Тесты TimeInterval, RiskFlag, TimelinePattern, RiskScore."""

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from work_activity_agent.domain.enums import RiskFlagType, RiskLevel
from work_activity_agent.domain.errors import InvalidTimeIntervalError
from work_activity_agent.domain.models.risk import (
    RiskFlag,
    RiskScore,
    TimeInterval,
    TimelinePattern,
)


class TestTimeInterval:
    def _ts(self, h: int) -> datetime:
        return datetime(2026, 4, 22, h, 0, 0, tzinfo=UTC)

    def test_valid_interval(self) -> None:
        i = TimeInterval(start=self._ts(10), end=self._ts(11))
        assert i.end > i.start

    def test_equal_bounds_allowed(self) -> None:
        # Точечный интервал — допустимо (например, единичный скриншот)
        TimeInterval(start=self._ts(10), end=self._ts(10))

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises((ValidationError, InvalidTimeIntervalError)):
            TimeInterval(start=self._ts(11), end=self._ts(10))

    def test_naive_datetime_rejected(self) -> None:
        naive = datetime(2026, 4, 22, 10, 0, 0)
        with pytest.raises(ValidationError):
            TimeInterval(start=naive, end=naive)

    @given(
        start_h=st.integers(min_value=0, max_value=23),
        delta_min=st.integers(min_value=0, max_value=600),
    )
    def test_property_valid_intervals_always_have_end_ge_start(
        self, start_h: int, delta_min: int
    ) -> None:
        start = datetime(2026, 4, 22, start_h, 0, 0, tzinfo=UTC)
        end = start + timedelta(minutes=delta_min)
        i = TimeInterval(start=start, end=end)
        assert i.end >= i.start


class TestRiskFlag:
    def _interval(self) -> TimeInterval:
        return TimeInterval(
            start=datetime(2026, 4, 22, 14, 20, 0, tzinfo=UTC),
            end=datetime(2026, 4, 22, 14, 50, 0, tzinfo=UTC),
        )

    def test_valid_flag(self) -> None:
        f = RiskFlag(
            type=RiskFlagType.STATIC_SCREEN_LONG_PERIOD,
            interval=self._interval(),
            severity=RiskLevel.MEDIUM,
            evidence="6 похожих скриншотов подряд",
            screenshot_ids=("scr_1", "scr_2"),
        )
        assert f.type == RiskFlagType.STATIC_SCREEN_LONG_PERIOD
        assert not f.requires_human_review

    def test_empty_screenshot_ids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RiskFlag(
                type=RiskFlagType.STATIC_SCREEN_LONG_PERIOD,
                interval=self._interval(),
                severity=RiskLevel.MEDIUM,
                evidence="x",
                screenshot_ids=(),
            )


class TestTimelinePattern:
    def test_valid(self) -> None:
        p = TimelinePattern(
            employee_id="dev_1",
            interval=TimeInterval(
                start=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
                end=datetime(2026, 4, 22, 11, 0, tzinfo=UTC),
            ),
            pattern="long_static_period",
            risk_level=RiskLevel.MEDIUM,
            reason="Экран не менялся 30 минут",
            requires_review=True,
            screenshot_ids=("scr_1", "scr_2", "scr_3"),
        )
        assert p.requires_review


class TestRiskScore:
    def test_valid(self) -> None:
        s = RiskScore(
            employee_id="dev_1",
            date=date(2026, 4, 22),
            score=42,
            level=RiskLevel.MEDIUM,
            components={"static_ratio": 0.21, "task_mismatch": 0.15},
            summary="Есть умеренный риск",
            recommended_action="Проверить с менеджером",
        )
        assert s.score == 42

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            RiskScore(
                employee_id="dev_1",
                date=date(2026, 4, 22),
                score=101,
                level=RiskLevel.HIGH,
                components={},
                summary="x",
                recommended_action="x",
            )

    def test_component_values_in_unit_interval(self) -> None:
        # компоненты должны быть нормализованы [0, 1]
        with pytest.raises(ValidationError):
            RiskScore(
                employee_id="dev_1",
                date=date(2026, 4, 22),
                score=50,
                level=RiskLevel.MEDIUM,
                components={"static_ratio": 1.5},
                summary="x",
                recommended_action="x",
            )
