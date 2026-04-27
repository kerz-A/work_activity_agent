"""Тесты RiskCalculator + property-based проверки."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from work_activity_agent.application.services.risk_calculator import RiskCalculator
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    RiskLevel,
)
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata

WEIGHTS = {
    "static_ratio": 0.25,
    "task_mismatch": 0.20,
    "non_work_ratio": 0.15,
    "no_progress": 0.15,
    "pattern_repetition": 0.10,
    "tracked_time_drift": 0.10,
    "manager_notes": 0.05,
}
THRESHOLDS = {"low": 30, "medium": 60}


def _screenshot(sid: str, hour: int, employee: str = "dev_1") -> Screenshot:
    return Screenshot(
        id=sid,
        path=Path(f"{sid}.png"),
        captured_at=datetime(2026, 4, 22, hour, 0, tzinfo=UTC),
        metadata=ScreenshotMetadata(
            employee_id=employee,
            project_id="proj",
            tracked_task_title="task",
            tracked_minutes=10,
        ),
    )


def _classification(sid: str, activity: ActivityType) -> ClassificationResult:
    return ClassificationResult(
        screenshot_id=sid,
        activity_type=activity,
        category="x",
        evidence=("e1",),
        confidence=0.9,
    )


def _relevance(sid: str, level: RelevanceLevel) -> RelevanceResult:
    return RelevanceResult(
        screenshot_id=sid,
        tracked_task="task",
        screenshot_activity="x",
        relevance=level,
        confidence=0.9,
    )


@pytest.fixture
def calc() -> RiskCalculator:
    return RiskCalculator(weights=WEIGHTS, thresholds=THRESHOLDS)


class TestRiskCalculator:
    def test_empty_screenshots_zero_score(self, calc: RiskCalculator) -> None:
        result = calc.compute_for_employee("dev_1", date(2026, 4, 22), [], {}, {})
        assert result.score == 0
        assert result.level == RiskLevel.LOW

    def test_all_productive_low_risk(self, calc: RiskCalculator) -> None:
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(5)]
        classifications = {
            s.id: _classification(s.id, ActivityType.PRODUCTIVE_WORK) for s in screenshots
        }
        relevances = {s.id: _relevance(s.id, RelevanceLevel.HIGH) for s in screenshots}
        result = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, relevances
        )
        assert result.level == RiskLevel.LOW

    def test_all_static_high_risk(self, calc: RiskCalculator) -> None:
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(10)]
        classifications = {
            s.id: _classification(s.id, ActivityType.IDLE_STATIC) for s in screenshots
        }
        result = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, {}
        )
        # static + no_progress → высокие компоненты
        assert result.score > 30

    def test_all_jobsearch_high_risk(self, calc: RiskCalculator) -> None:
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(5)]
        classifications = {
            s.id: _classification(s.id, ActivityType.JOB_SEARCH_SIGNAL) for s in screenshots
        }
        relevances = {s.id: _relevance(s.id, RelevanceLevel.LOW) for s in screenshots}
        result = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, relevances
        )
        assert result.level in {RiskLevel.MEDIUM, RiskLevel.HIGH}

    @given(
        n_static=st.integers(min_value=0, max_value=10),
        n_productive=st.integers(min_value=0, max_value=10),
        n_jobsearch=st.integers(min_value=0, max_value=10),
    )
    def test_score_always_in_0_100_range(
        self, n_static: int, n_productive: int, n_jobsearch: int
    ) -> None:
        calc = RiskCalculator(weights=WEIGHTS, thresholds=THRESHOLDS)
        screenshots: list[Screenshot] = []
        classifications: dict[str, ClassificationResult] = {}
        idx = 0

        for _ in range(n_static):
            s = _screenshot(f"s_static_{idx}", 9 + (idx % 8))
            screenshots.append(s)
            classifications[s.id] = _classification(s.id, ActivityType.IDLE_STATIC)
            idx += 1
        for _ in range(n_productive):
            s = _screenshot(f"s_prod_{idx}", 9 + (idx % 8))
            screenshots.append(s)
            classifications[s.id] = _classification(s.id, ActivityType.PRODUCTIVE_WORK)
            idx += 1
        for _ in range(n_jobsearch):
            s = _screenshot(f"s_job_{idx}", 9 + (idx % 8))
            screenshots.append(s)
            classifications[s.id] = _classification(s.id, ActivityType.JOB_SEARCH_SIGNAL)
            idx += 1

        result = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, {}
        )
        assert 0 <= result.score <= 100

    def test_thresholds_must_be_monotonic(self) -> None:
        """Конфиг с low >= medium даст _level() never-MEDIUM — запрещаем явно."""
        with pytest.raises(ValueError, match="thresholds invalid"):
            RiskCalculator(weights=WEIGHTS, thresholds={"low": 60, "medium": 30})

    def test_threshold_boundaries(self, calc: RiskCalculator) -> None:
        # 100% static → score должен попасть в HIGH
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(5)]
        classifications = {
            s.id: _classification(s.id, ActivityType.IDLE_STATIC) for s in screenshots
        }
        relevances = {s.id: _relevance(s.id, RelevanceLevel.LOW) for s in screenshots}
        result = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, relevances
        )
        assert result.level == RiskLevel.HIGH
