"""RiskCalculator — детерминистичный калькулятор Time Farming Risk Score (ТЗ §5).

Чистая математика. Покрывается hypothesis property-based тестами.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    RiskLevel,
)
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.risk import RiskScore
from work_activity_agent.domain.models.screenshot import Screenshot

# Категории, считающиеся "статичными" для метрики static_ratio
_STATIC_CATEGORIES = frozenset({ActivityType.IDLE_STATIC.value})

# Категории, считающиеся "нерабочими" для метрики non_work_ratio
_NON_WORK_CATEGORIES = frozenset(
    {
        ActivityType.NON_WORK.value,
        ActivityType.JOB_SEARCH_SIGNAL.value,
        ActivityType.OTHER_PROJECT_SIGNAL.value,
    }
)

# Категории "продуктивных", по которым считаем no_progress (если их мало)
_PRODUCTIVE_CATEGORIES = frozenset(
    {
        ActivityType.PRODUCTIVE_WORK.value,
        ActivityType.PROJECT_COMMUNICATION.value,
        ActivityType.RESEARCH.value,
        ActivityType.ADMIN_WORK.value,
    }
)


class RiskCalculator:
    """Считает Risk Score из метрик активности."""

    def __init__(
        self,
        weights: Mapping[str, float],
        thresholds: Mapping[str, int],
    ) -> None:
        self._weights = dict(weights)
        self._thresholds = dict(thresholds)

    def compute_for_employee(
        self,
        employee_id: str,
        report_date: date,
        screenshots: list[Screenshot],
        classifications: dict[str, ClassificationResult],
        relevances: dict[str, RelevanceResult],
    ) -> RiskScore:
        """Посчитать RiskScore по метрикам сотрудника."""
        components = self._compute_components(screenshots, classifications, relevances)
        score = self._weighted_score(components)
        level = self._level(score)
        summary = self._build_summary(components, score, level)
        recommended = self._build_recommendation(level, components)

        return RiskScore(
            employee_id=employee_id,
            date=report_date,
            score=score,
            level=level,
            components=components,
            summary=summary,
            recommended_action=recommended,
        )

    def _compute_components(
        self,
        screenshots: list[Screenshot],
        classifications: dict[str, ClassificationResult],
        relevances: dict[str, RelevanceResult],
    ) -> dict[str, float]:
        n = len(screenshots)
        if n == 0:
            return {key: 0.0 for key in self._weights}

        static_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id)) and cls.activity_type.value in _STATIC_CATEGORIES
        )
        non_work_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id))
            and cls.activity_type.value in _NON_WORK_CATEGORIES
        )
        productive_count = sum(
            1
            for s in screenshots
            if (cls := classifications.get(s.id))
            and cls.activity_type.value in _PRODUCTIVE_CATEGORIES
        )

        # task_mismatch: доля скринов с relevance=low
        low_relevance_count = sum(
            1 for r in relevances.values() if r.relevance == RelevanceLevel.LOW
        )
        # tracked_time_drift: пока нет реальных данных о tracked_minutes vs скриншотах
        # — заглушка, будем считать долю скринов без metadata.tracked_minutes
        tracked_drift_count = sum(1 for s in screenshots if s.metadata.tracked_minutes is None)

        return {
            "static_ratio": static_count / n,
            "task_mismatch": low_relevance_count / n if relevances else 0.0,
            "non_work_ratio": non_work_count / n,
            "no_progress": 1.0 - (productive_count / n),
            "pattern_repetition": 0.0,  # требует cross-day данных, в MVP = 0
            "tracked_time_drift": tracked_drift_count / n,
            "manager_notes": 0.0,  # заглушка — нет UI менеджера
        }

    def _weighted_score(self, components: dict[str, float]) -> int:
        total = sum(self._weights.get(key, 0.0) * value for key, value in components.items())
        return max(0, min(100, round(total * 100)))

    def _level(self, score: int) -> RiskLevel:
        if score < self._thresholds.get("low", 30):
            return RiskLevel.LOW
        if score < self._thresholds.get("medium", 60):
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    def _build_summary(self, components: dict[str, float], score: int, level: RiskLevel) -> str:
        parts = [f"Risk score {score}/100 ({level.value})."]
        if components.get("static_ratio", 0) > 0.3:
            parts.append(f"Высокая доля статичных скринов ({components['static_ratio']:.0%}).")
        if components.get("non_work_ratio", 0) > 0.2:
            parts.append(f"Доля нерабочих сайтов: {components['non_work_ratio']:.0%}.")
        if components.get("task_mismatch", 0) > 0.2:
            parts.append(f"Несоответствие задаче: {components['task_mismatch']:.0%} скринов.")
        if level == RiskLevel.LOW:
            parts.append("Признаков нарушения не обнаружено.")
        return " ".join(parts)

    def _build_recommendation(self, level: RiskLevel, components: dict[str, float]) -> str:
        if level == RiskLevel.LOW:
            return "Дополнительных действий не требуется."
        actions = ["Запросить ручную проверку менеджером."]
        if components.get("static_ratio", 0) > 0.3:
            actions.append("Уточнить контекст статичных периодов (созвон, чтение, перерыв).")
        if components.get("non_work_ratio", 0) > 0.2:
            actions.append("Обсудить с сотрудником видимые нерабочие активности.")
        return " ".join(actions)
