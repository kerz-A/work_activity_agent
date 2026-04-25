"""Тесты TimelineGrouper."""

from datetime import UTC, datetime
from pathlib import Path

from work_activity_agent.application.services.timeline_grouper import TimelineGrouper
from work_activity_agent.domain.enums import ActivityType
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata


def _ss(sid: str, hour: int, minute: int = 0, employee: str | None = "dev_1") -> Screenshot:
    return Screenshot(
        id=sid,
        path=Path(f"{sid}.png"),
        captured_at=datetime(2026, 4, 22, hour, minute, tzinfo=UTC),
        metadata=ScreenshotMetadata(employee_id=employee),
    )


def _cls(sid: str, activity: ActivityType) -> ClassificationResult:
    return ClassificationResult(
        screenshot_id=sid,
        activity_type=activity,
        category="x",
        evidence=("e",),
        confidence=0.9,
    )


class TestGroupByEmployeeAndHour:
    def test_groups_by_employee(self) -> None:
        screenshots = [
            _ss("s1", 9, employee="a"),
            _ss("s2", 9, employee="b"),
        ]
        groups = TimelineGrouper().group_by_employee_and_hour(screenshots)
        assert len(groups) == 2
        assert {g.employee_id for g in groups} == {"a", "b"}

    def test_groups_by_hour(self) -> None:
        screenshots = [
            _ss("s1", 9, 0),
            _ss("s2", 9, 30),
            _ss("s3", 10, 0),
        ]
        groups = TimelineGrouper().group_by_employee_and_hour(screenshots)
        assert len(groups) == 2
        assert len(groups[0].screenshots) == 2

    def test_unknown_employee(self) -> None:
        screenshots = [_ss("s1", 9, employee=None)]
        groups = TimelineGrouper().group_by_employee_and_hour(screenshots)
        assert groups[0].employee_id == "_unknown"

    def test_screenshots_sorted_within_group(self) -> None:
        screenshots = [
            _ss("s_late", 9, 30),
            _ss("s_early", 9, 5),
        ]
        groups = TimelineGrouper().group_by_employee_and_hour(screenshots)
        ids = [s.id for s in groups[0].screenshots]
        assert ids == ["s_early", "s_late"]


class TestFindConsecutiveRuns:
    def test_finds_run_above_threshold(self) -> None:
        screenshots = [_ss(f"s{i}", 9, i) for i in range(5)]
        classifications = {s.id: _cls(s.id, ActivityType.IDLE_STATIC) for s in screenshots}
        runs = TimelineGrouper().find_consecutive_runs(
            screenshots,
            classifications,
            target_categories={"idle_static"},
            min_count=4,
        )
        assert len(runs) == 1
        assert len(runs[0]) == 5

    def test_skips_run_below_threshold(self) -> None:
        screenshots = [_ss(f"s{i}", 9, i) for i in range(2)]
        classifications = {s.id: _cls(s.id, ActivityType.IDLE_STATIC) for s in screenshots}
        runs = TimelineGrouper().find_consecutive_runs(
            screenshots,
            classifications,
            target_categories={"idle_static"},
            min_count=4,
        )
        assert runs == []

    def test_breaks_on_other_category(self) -> None:
        s1 = _ss("s1", 9, 0)
        s2 = _ss("s2", 9, 5)
        s3 = _ss("s3", 9, 10)
        s4 = _ss("s4", 9, 15)
        classifications = {
            s1.id: _cls(s1.id, ActivityType.IDLE_STATIC),
            s2.id: _cls(s2.id, ActivityType.IDLE_STATIC),
            s3.id: _cls(s3.id, ActivityType.PRODUCTIVE_WORK),  # break
            s4.id: _cls(s4.id, ActivityType.IDLE_STATIC),
        }
        runs = TimelineGrouper().find_consecutive_runs(
            [s1, s2, s3, s4],
            classifications,
            target_categories={"idle_static"},
            min_count=2,
        )
        assert len(runs) == 1  # только первая пара
