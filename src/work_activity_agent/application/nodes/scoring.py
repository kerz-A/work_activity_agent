"""Узел Scoring: считает RiskScore и WorkActivityScore по сотрудникам."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date

from work_activity_agent.application.services.risk_calculator import RiskCalculator
from work_activity_agent.application.services.work_activity_calculator import (
    WorkActivityCalculator,
)
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.models.productivity import WorkActivityScore
from work_activity_agent.domain.models.risk import RiskScore
from work_activity_agent.domain.models.screenshot import Screenshot
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_scoring_node(deps: Deps) -> Callable[[AgentState], AgentState]:
    log = get_logger("scoring")
    risk_calc = RiskCalculator(
        weights=deps.settings.risk.risk_weights,
        thresholds=deps.settings.risk.risk_thresholds,
    )
    work_calc = WorkActivityCalculator(
        weights=deps.settings.risk.work_activity_weights,
        thresholds=deps.settings.risk.work_activity_thresholds,
    )

    def scoring_node(state: AgentState) -> AgentState:
        log.info("scoring.start", run_id=state.run_id)

        # Группируем скрины по (employee_id, date)
        groups: dict[tuple[str, date], list[Screenshot]] = defaultdict(list)
        for s in state.screenshots:
            employee = s.metadata.employee_id or "_unknown"
            groups[(employee, s.captured_at.date())].append(s)

        # Один проход по timeline_patterns вместо линейной фильтрации в каждой
        # итерации цикла по сотрудникам.
        patterns_by_employee: dict[str, list[object]] = defaultdict(list)
        for pattern in state.timeline_patterns:
            patterns_by_employee[pattern.employee_id].append(pattern)

        risk_scores: dict[str, RiskScore] = {}
        work_scores: dict[str, WorkActivityScore] = {}

        for (employee_id, report_date), screenshots in groups.items():
            risk_score = risk_calc.compute_for_employee(
                employee_id=employee_id,
                report_date=report_date,
                screenshots=screenshots,
                classifications=state.classifications,
                relevances=state.relevances,
            )
            # Считаем сколько risk_flags применимо к этому сотруднику
            employee_patterns = patterns_by_employee.get(employee_id, [])
            work_score = work_calc.compute_for_employee(
                employee_id=employee_id,
                report_date=report_date,
                screenshots=screenshots,
                classifications=state.classifications,
                relevances=state.relevances,
                risk_flags_count=len(employee_patterns),
            )

            key = f"{employee_id}__{report_date.isoformat()}"
            risk_scores[key] = risk_score
            work_scores[key] = work_score

            log.info(
                "scoring.computed",
                employee=employee_id,
                date=report_date.isoformat(),
                risk_score=risk_score.score,
                risk_level=risk_score.level.value,
                work_score=work_score.score,
                work_level=work_score.level.value,
            )

        log.info("scoring.done", employees=len(risk_scores))
        return state.model_copy(
            update={
                "risk_scores": risk_scores,
                "work_activity_scores": work_scores,
            }
        )

    return scoring_node
