"""Тесты WorkActivityCalculator."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from work_activity_agent.application.services.work_activity_calculator import (
    WorkActivityCalculator,
)
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    WorkActivityLevel,
)
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata

WEIGHTS = {
    "task_alignment": 0.25,
    "result_evidence": 0.20,
    "productive_tools_ratio": 0.15,
    "screen_dynamics": 0.15,
    "project_communication_ratio": 0.10,
    "work_regularity": 0.10,
    "no_risk_flags": 0.05,
}
THRESHOLDS = {"low": 40, "medium": 70}


def _screenshot(sid: str, hour: int) -> Screenshot:
    return Screenshot(
        id=sid,
        path=Path(f"{sid}.png"),
        captured_at=datetime(2026, 4, 22, hour, 0, tzinfo=UTC),
        metadata=ScreenshotMetadata(employee_id="dev_1", project_id="proj"),
    )


def _classification(sid: str, activity: ActivityType) -> ClassificationResult:
    return ClassificationResult(
        screenshot_id=sid,
        activity_type=activity,
        category="x",
        evidence=("e",),
        confidence=0.9,
    )


def _relevance(sid: str, level: RelevanceLevel) -> RelevanceResult:
    return RelevanceResult(
        screenshot_id=sid,
        tracked_task="t",
        screenshot_activity="x",
        relevance=level,
        confidence=0.9,
    )


@pytest.fixture
def calc() -> WorkActivityCalculator:
    return WorkActivityCalculator(weights=WEIGHTS, thresholds=THRESHOLDS)


class TestWorkActivityCalculator:
    def test_empty_screenshots(self, calc: WorkActivityCalculator) -> None:
        r = calc.compute_for_employee("dev_1", date(2026, 4, 22), [], {}, {})
        assert r.score == 0
        assert r.level == WorkActivityLevel.LOW

    def test_high_productive_high_score(self, calc: WorkActivityCalculator) -> None:
        # 9 productive в разных часах = 1.0 task_alignment + 1.0 productive_tools + 1.0 dynamics
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(9)]
        classifications = {
            s.id: _classification(s.id, ActivityType.PRODUCTIVE_WORK) for s in screenshots
        }
        relevances = {s.id: _relevance(s.id, RelevanceLevel.HIGH) for s in screenshots}
        r = calc.compute_for_employee(
            "dev_1", date(2026, 4, 22), screenshots, classifications, relevances
        )
        assert r.score >= 65

    def test_static_low_screen_dynamics(self, calc: WorkActivityCalculator) -> None:
        screenshots = [_screenshot(f"s{i}", 9) for i in range(5)]
        classifications = {
            s.id: _classification(s.id, ActivityType.IDLE_STATIC) for s in screenshots
        }
        r = calc.compute_for_employee("dev_1", date(2026, 4, 22), screenshots, classifications, {})
        # screen_dynamics = 0 (все static)
        assert r.components.screen_dynamics == 0.0

    def test_risk_flags_reduce_score(self, calc: WorkActivityCalculator) -> None:
        screenshots = [_screenshot(f"s{i}", 9 + i) for i in range(5)]
        classifications = {
            s.id: _classification(s.id, ActivityType.PRODUCTIVE_WORK) for s in screenshots
        }
        relevances = {s.id: _relevance(s.id, RelevanceLevel.HIGH) for s in screenshots}
        r_no_flags = calc.compute_for_employee(
            "dev_1",
            date(2026, 4, 22),
            screenshots,
            classifications,
            relevances,
            risk_flags_count=0,
        )
        r_with_flags = calc.compute_for_employee(
            "dev_1",
            date(2026, 4, 22),
            screenshots,
            classifications,
            relevances,
            risk_flags_count=3,
        )
        assert r_with_flags.score < r_no_flags.score

    def test_score_in_0_100(self, calc: WorkActivityCalculator) -> None:
        for n in (0, 1, 5, 10, 20):
            screenshots = [_screenshot(f"s{i}", 9 + (i % 9)) for i in range(n)]
            classifications = {
                s.id: _classification(s.id, ActivityType.PRODUCTIVE_WORK) for s in screenshots
            }
            r = calc.compute_for_employee(
                "dev_1", date(2026, 4, 22), screenshots, classifications, {}
            )
            assert 0 <= r.score <= 100

    def test_note_present(self, calc: WorkActivityCalculator) -> None:
        r = calc.compute_for_employee("dev_1", date(2026, 4, 22), [], {}, {})
        assert r.note is not None
        assert "result_evidence" in r.note.lower()
