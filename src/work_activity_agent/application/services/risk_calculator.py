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
from work_activity_agent.domain.models.ocr_signals import OCRSignals
from work_activity_agent.domain.models.risk import RiskScore
from work_activity_agent.domain.models.screenshot import Screenshot

# Категории доменов, попадание в которые поднимает domain_blacklist_hits.
# Соответствует ключам в configs/domain_rules.yaml: domain_categories.
_RISK_DOMAIN_CATEGORIES = frozenset({"job_search", "entertainment", "personal_messaging"})

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


def _validate_thresholds(thresholds: dict[str, int], *, name: str) -> None:
    """Проверить, что low < medium. Конфиг с обратным порядком сделает _level()
    некорректным (medium-уровень никогда не сработает), но без явной ошибки."""
    if "low" in thresholds and "medium" in thresholds and thresholds["low"] >= thresholds["medium"]:
        raise ValueError(
            f"{name}: thresholds invalid — "
            f"low ({thresholds['low']}) must be < medium ({thresholds['medium']})"
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
        _validate_thresholds(self._thresholds, name="RiskCalculator")

    def compute_for_employee(
        self,
        employee_id: str,
        report_date: date,
        screenshots: list[Screenshot],
        classifications: dict[str, ClassificationResult],
        relevances: dict[str, RelevanceResult],
        ocr_signals: dict[str, OCRSignals] | None = None,
    ) -> RiskScore:
        """Посчитать RiskScore по метрикам сотрудника."""
        components = self._compute_components(
            screenshots, classifications, relevances, ocr_signals or {}
        )
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
        ocr_signals: dict[str, OCRSignals],
    ) -> dict[str, float]:
        n = len(screenshots)
        if n == 0:
            return {key: 0.0 for key in self._weights}

        # Один проход по screenshots: считаем все классификационные счётчики и
        # tracked_drift сразу. Раньше было 4 раздельных sum() прохода.
        static_count = 0
        non_work_count = 0
        productive_count = 0
        tracked_drift_count = 0
        domain_blacklist_count = 0
        screenshot_ids: set[str] = set()
        for s in screenshots:
            screenshot_ids.add(s.id)
            if s.metadata.tracked_minutes is None:
                tracked_drift_count += 1
            cls = classifications.get(s.id)
            if cls is not None:
                activity = cls.activity_type.value
                if activity in _STATIC_CATEGORIES:
                    static_count += 1
                if activity in _NON_WORK_CATEGORIES:
                    non_work_count += 1
                if activity in _PRODUCTIVE_CATEGORIES:
                    productive_count += 1
            # Detection через OCR — независимо от LLM-классификатора.
            ocr = ocr_signals.get(s.id)
            if ocr is not None and ocr.domain_category in _RISK_DOMAIN_CATEGORIES:
                domain_blacklist_count += 1

        # task_mismatch: доля скринов ЭТОГО сотрудника с relevance=low.
        # Фильтруем relevances только по screenshot_ids этого сотрудника — иначе при
        # глобальном словаре relevances из state знаменатель ломается.
        low_relevance_count = sum(
            1
            for sid, r in relevances.items()
            if sid in screenshot_ids and r.relevance == RelevanceLevel.LOW
        )

        # Защитный clamp на случай неожиданных делений > 1.0 (например, дубликаты в данных).
        def _clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        # domain_blacklist_hits: 10% скринов в blacklist → фул-вес.
        # Это даёт risk-floor независимо от качества LLM-классификации.
        return {
            "static_ratio": _clamp(static_count / n),
            "task_mismatch": _clamp(low_relevance_count / n) if relevances else 0.0,
            "non_work_ratio": _clamp(non_work_count / n),
            "no_progress": _clamp(1.0 - (productive_count / n)),
            "pattern_repetition": 0.0,  # требует cross-day данных, в MVP = 0
            "tracked_time_drift": _clamp(tracked_drift_count / n),
            "manager_notes": 0.0,  # заглушка — нет UI менеджера
            "domain_blacklist_hits": _clamp(domain_blacklist_count / max(1, n * 0.1)),
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
        if components.get("domain_blacklist_hits", 0) > 0:
            parts.append(
                "OCR обнаружил скрины с доменами вне рабочего профиля "
                "(job_search/entertainment/personal_messaging)."
            )
        if level == RiskLevel.LOW and components.get("domain_blacklist_hits", 0) == 0:
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
