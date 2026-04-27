"""Property-based тесты для TimelineGrouper.

Проверяем инварианты алгоритма группировки и поиска consecutive runs:
не зависят от конкретных значений данных.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from work_activity_agent.application.services.timeline_grouper import TimelineGrouper
from work_activity_agent.domain.enums import ActivityType
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata

_BASE_DT = datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
_ACTIVITIES = list(ActivityType)


def _make_screenshot(idx: int, employee: str, minute_offset: int) -> Screenshot:
    return Screenshot(
        id=f"s{idx}",
        path=Path(f"s{idx}.png"),
        captured_at=_BASE_DT + timedelta(minutes=minute_offset),
        metadata=ScreenshotMetadata(employee_id=employee),
    )


def _make_classification(sid: str, activity: ActivityType) -> ClassificationResult:
    return ClassificationResult(
        screenshot_id=sid,
        activity_type=activity,
        category="x",
        evidence=("e",),
        confidence=0.5,
    )


screenshot_count = st.integers(min_value=0, max_value=30)
min_count_strategy = st.integers(min_value=1, max_value=10)
employees_strategy = st.lists(
    st.sampled_from(["dev_1", "dev_2", "dev_3"]),
    min_size=1,
    max_size=30,
)
activities_strategy = st.lists(st.sampled_from(_ACTIVITIES), min_size=0, max_size=30)


@settings(
    max_examples=80,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    minute_offsets=st.lists(st.integers(min_value=0, max_value=600), min_size=0, max_size=30),
    employees=employees_strategy,
)
def test_group_by_employee_and_hour_partitions_input(
    minute_offsets: list[int], employees: list[str]
) -> None:
    """Каждый скрин попадает ровно в одну группу; интервал группы = 1 час."""
    n = min(len(minute_offsets), len(employees))
    screenshots = [_make_screenshot(i, employees[i], minute_offsets[i]) for i in range(n)]

    groups = TimelineGrouper().group_by_employee_and_hour(screenshots)

    total = sum(len(g.screenshots) for g in groups)
    assert total == n
    for g in groups:
        assert g.interval_end - g.interval_start == timedelta(hours=1)
        assert g.interval_start.minute == 0
        assert g.interval_start.second == 0
        for s in g.screenshots:
            assert g.interval_start <= s.captured_at < g.interval_end
            assert s.metadata.employee_id == g.employee_id


@settings(
    max_examples=80,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    activities=activities_strategy,
    min_count=min_count_strategy,
)
def test_find_consecutive_runs_respects_min_count(
    activities: list[ActivityType], min_count: int
) -> None:
    """Каждый возвращённый run длины >= min_count, и все его элементы из target_categories."""
    screenshots = [_make_screenshot(i, "dev_1", i) for i in range(len(activities))]
    classifications = {
        s.id: _make_classification(s.id, a) for s, a in zip(screenshots, activities, strict=True)
    }
    target = {ActivityType.IDLE_STATIC.value}

    runs = TimelineGrouper().find_consecutive_runs(
        screenshots, classifications, target_categories=target, min_count=min_count
    )

    for run in runs:
        assert len(run) >= min_count
        for s in run:
            assert classifications[s.id].activity_type.value in target


@settings(
    max_examples=80,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(activities=activities_strategy, min_count=min_count_strategy)
def test_runs_total_length_does_not_exceed_target_count(
    activities: list[ActivityType], min_count: int
) -> None:
    """Сумма длин runs ≤ числу скринов с target activity."""
    screenshots = [_make_screenshot(i, "dev_1", i) for i in range(len(activities))]
    classifications = {
        s.id: _make_classification(s.id, a) for s, a in zip(screenshots, activities, strict=True)
    }
    target = {ActivityType.IDLE_STATIC.value}

    runs = TimelineGrouper().find_consecutive_runs(
        screenshots, classifications, target_categories=target, min_count=min_count
    )
    total_in_runs = sum(len(r) for r in runs)
    target_total = sum(1 for a in activities if a.value in target)

    assert total_in_runs <= target_total


@settings(max_examples=20, deadline=None)
@given(activities=activities_strategy)
def test_empty_target_returns_no_runs(activities: list[ActivityType]) -> None:
    """С пустым набором target категорий — ни одного run."""
    screenshots = [_make_screenshot(i, "dev_1", i) for i in range(len(activities))]
    classifications = {
        s.id: _make_classification(s.id, a) for s, a in zip(screenshots, activities, strict=True)
    }

    runs = TimelineGrouper().find_consecutive_runs(
        screenshots, classifications, target_categories=set(), min_count=1
    )
    assert runs == []
