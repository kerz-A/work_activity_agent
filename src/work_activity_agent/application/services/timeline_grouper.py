"""TimelineGrouper — группирует скриншоты для Timeline-анализа.

Чистая логика, тестируется property-based.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import NamedTuple

from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.screenshot import Screenshot


class ScreenshotGroup(NamedTuple):
    """Группа скриншотов одного сотрудника за интервал времени."""

    employee_id: str
    interval_start: datetime
    interval_end: datetime
    screenshots: tuple[Screenshot, ...]


class TimelineGrouper:
    """Группирует скриншоты по (employee_id, hour) для детекции паттернов."""

    def group_by_employee_and_hour(
        self,
        screenshots: Sequence[Screenshot],
    ) -> list[ScreenshotGroup]:
        """Сгруппировать скриншоты по сотруднику в часовые интервалы.

        Скриншоты без employee_id попадают в группу "_unknown".
        Группы отсортированы по (employee_id, interval_start).
        """
        buckets: dict[tuple[str, datetime], list[Screenshot]] = defaultdict(list)

        for s in screenshots:
            employee = s.metadata.employee_id or "_unknown"
            hour_start = s.captured_at.replace(minute=0, second=0, microsecond=0)
            buckets[(employee, hour_start)].append(s)

        groups: list[ScreenshotGroup] = []
        for (employee, start), items in sorted(buckets.items()):
            sorted_items = sorted(items, key=lambda x: x.captured_at)
            groups.append(
                ScreenshotGroup(
                    employee_id=employee,
                    interval_start=start,
                    interval_end=start + timedelta(hours=1),
                    screenshots=tuple(sorted_items),
                )
            )
        return groups

    def find_consecutive_runs(
        self,
        screenshots: Sequence[Screenshot],
        classifications: dict[str, ClassificationResult],
        target_categories: set[str],
        *,
        min_count: int = 3,
    ) -> list[tuple[Screenshot, ...]]:
        """Найти последовательности из >=min_count скриншотов одного из target_categories.

        Скриншоты должны идти подряд по времени (без других категорий между ними).
        """
        runs: list[tuple[Screenshot, ...]] = []
        current: list[Screenshot] = []

        sorted_shots = sorted(screenshots, key=lambda s: s.captured_at)
        for s in sorted_shots:
            cls = classifications.get(s.id)
            if cls and cls.activity_type.value in target_categories:
                current.append(s)
            else:
                if len(current) >= min_count:
                    runs.append(tuple(current))
                current = []

        if len(current) >= min_count:
            runs.append(tuple(current))

        return runs
