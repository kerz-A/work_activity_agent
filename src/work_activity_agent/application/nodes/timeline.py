"""Узел Timeline: детектит паттерны по сериям скриншотов (ТЗ §6)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

from work_activity_agent.application.services.timeline_grouper import (
    ScreenshotGroup,
    TimelineGrouper,
)
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import ActivityType, RiskLevel
from work_activity_agent.domain.models.risk import TimeInterval, TimelinePattern
from work_activity_agent.domain.models.screenshot import Screenshot
from work_activity_agent.infrastructure.observability.logging import get_logger


def make_timeline_node(deps: Deps) -> Callable[[AgentState], Awaitable[AgentState]]:
    log = get_logger("timeline")
    grouper = TimelineGrouper()

    timeline_cfg = deps.settings.risk.timeline_config
    static_cfg = timeline_cfg.get("static_screen", {}) if timeline_cfg else {}
    burst_cfg = timeline_cfg.get("burst_detection", {}) if timeline_cfg else {}

    static_min_consecutive = int(static_cfg.get("min_consecutive", 4))
    job_search_burst_min = int(burst_cfg.get("min_count_per_hour", 3))

    async def timeline_node(state: AgentState) -> AgentState:
        log.info("timeline.start", run_id=state.run_id)

        groups = grouper.group_by_employee_and_hour(state.screenshots)
        patterns: list[TimelinePattern] = []

        for group in groups:
            patterns.extend(_detect_static_runs(group, state, static_min_consecutive))
            patterns.extend(_detect_job_search_burst(group, state, job_search_burst_min))

        log.info("timeline.done", patterns_found=len(patterns))
        return state.model_copy(update={"timeline_patterns": patterns})

    return timeline_node


def _detect_static_runs(
    group: ScreenshotGroup,
    state: AgentState,
    min_consecutive: int,
) -> list[TimelinePattern]:
    """Найти серии IDLE_STATIC одного сотрудника."""
    runs = TimelineGrouper().find_consecutive_runs(
        group.screenshots,
        state.classifications,
        target_categories={ActivityType.IDLE_STATIC.value},
        min_count=min_consecutive,
    )
    return [
        _run_to_pattern(
            group.employee_id,
            run,
            "long_static_period",
            RiskLevel.MEDIUM,
            "Экран почти не менялся длительное время",
        )
        for run in runs
    ]


def _detect_job_search_burst(
    group: ScreenshotGroup,
    state: AgentState,
    min_count: int,
) -> list[TimelinePattern]:
    """Найти концентрацию JOB_SEARCH_SIGNAL в группе."""
    job_search_shots = [
        s
        for s in group.screenshots
        if (cls := state.classifications.get(s.id))
        and cls.activity_type == ActivityType.JOB_SEARCH_SIGNAL
    ]
    if len(job_search_shots) < min_count:
        return []
    return [
        _run_to_pattern(
            group.employee_id,
            tuple(job_search_shots),
            "job_search_burst",
            RiskLevel.HIGH,
            f"Серия из {len(job_search_shots)} скринов с признаками поиска работы за час",
        )
    ]


def _run_to_pattern(
    employee_id: str,
    run: tuple[Screenshot, ...],
    pattern_name: str,
    risk_level: RiskLevel,
    reason: str,
) -> TimelinePattern:
    interval = TimeInterval(
        start=run[0].captured_at,
        end=run[-1].captured_at + timedelta(minutes=5),
    )
    return TimelinePattern(
        employee_id=employee_id,
        interval=interval,
        pattern=pattern_name,
        risk_level=risk_level,
        reason=reason,
        requires_review=True,
        screenshot_ids=tuple(s.id for s in run),
    )
