"""WorkActivityCalculator — детерминистичный калькулятор Work Activity Score (ТЗ §14)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from work_activity_agent.application.services.risk_calculator import _validate_thresholds
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    WorkActivityLevel,
)
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.productivity import (
    ActivityComponents,
    WorkActivityScore,
)
from work_activity_agent.domain.models.screenshot import Screenshot

_PRODUCTIVE_TOOLS = frozenset(
    {
        ActivityType.PRODUCTIVE_WORK.value,
        ActivityType.RESEARCH.value,
        ActivityType.ADMIN_WORK.value,
    }
)


class WorkActivityCalculator:
    """Считает Work Activity Score (продуктивность 0-100, выше = лучше)."""

    def __init__(
        self,
        weights: Mapping[str, float],
        thresholds: Mapping[str, int],
    ) -> None:
        self._weights = dict(weights)
        self._thresholds = dict(thresholds)
        _validate_thresholds(self._thresholds, name="WorkActivityCalculator")

    def compute_for_employee(
        self,
        employee_id: str,
        report_date: date,
        screenshots: list[Screenshot],
        classifications: dict[str, ClassificationResult],
        relevances: dict[str, RelevanceResult],
        risk_flags_count: int = 0,
    ) -> WorkActivityScore:
        components = self._compute_components(
            screenshots, classifications, relevances, risk_flags_count
        )
        score = self._weighted_score(components)
        level = self._level(score)
        note = "result_evidence not available in MVP (no Git/Jira integration)"

        return WorkActivityScore(
            employee_id=employee_id,
            date=report_date,
            score=score,
            level=level,
            components=components,
            note=note,
        )

    def _compute_components(
        self,
        screenshots: list[Screenshot],
        classifications: dict[str, ClassificationResult],
        relevances: dict[str, RelevanceResult],
        risk_flags_count: int,
    ) -> ActivityComponents:
        n = len(screenshots)
        if n == 0:
            return ActivityComponents()

        # task_alignment: доля high+medium relevance ОТ ОБЩЕГО ЧИСЛА СКРИНОВ.
        # Считаем только relevances, относящиеся к скринам этого сотрудника
        # (relevances может приходить глобальным dict из state — отфильтруем).
        screenshot_ids = {s.id for s in screenshots}
        if relevances:
            aligned = sum(
                1
                for sid, r in relevances.items()
                if sid in screenshot_ids
                and r.relevance in {RelevanceLevel.HIGH, RelevanceLevel.MEDIUM}
            )
            task_alignment = aligned / n
        else:
            task_alignment = 0.0

        # productive_tools_ratio
        productive_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id)) and cls.activity_type.value in _PRODUCTIVE_TOOLS
        )
        productive_tools_ratio = productive_count / n

        # screen_dynamics: 1 - доля static
        static_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id)) and cls.activity_type == ActivityType.IDLE_STATIC
        )
        screen_dynamics = 1.0 - (static_count / n)

        # project_communication_ratio
        comm_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id))
            and cls.activity_type == ActivityType.PROJECT_COMMUNICATION
        )
        project_communication_ratio = comm_count / n

        # work_regularity: чем равномернее распределение по часам, тем лучше (1 - std)
        work_regularity = self._compute_regularity(screenshots)

        # no_risk_flags: 1.0 если 0 флагов, убывает с ростом
        no_risk_flags = max(0.0, 1.0 - (risk_flags_count * 0.2))

        return ActivityComponents(
            task_alignment=task_alignment,
            result_evidence=0.0,  # MVP: нет Git/Jira
            productive_tools_ratio=productive_tools_ratio,
            screen_dynamics=screen_dynamics,
            project_communication_ratio=project_communication_ratio,
            work_regularity=work_regularity,
            no_risk_flags=no_risk_flags,
        )

    @staticmethod
    def _compute_regularity(screenshots: list[Screenshot]) -> float:
        """1.0 если по 1+ скрина в каждый час рабочего дня (9-18), убывает с разрывами."""
        if not screenshots:
            return 0.0
        hours_with_activity = {s.captured_at.hour for s in screenshots}
        # 9 рабочих часов в day
        return min(1.0, len(hours_with_activity) / 9.0)

    def _weighted_score(self, components: ActivityComponents) -> int:
        component_dict = components.model_dump()
        total = 0.0
        for key, value in component_dict.items():
            weight = self._weights.get(key, 0.0)
            total += weight * float(value)
        return max(0, min(100, round(total * 100)))

    def _level(self, score: int) -> WorkActivityLevel:
        if score < self._thresholds.get("low", 40):
            return WorkActivityLevel.LOW
        if score < self._thresholds.get("medium", 70):
            return WorkActivityLevel.MEDIUM
        return WorkActivityLevel.HIGH
