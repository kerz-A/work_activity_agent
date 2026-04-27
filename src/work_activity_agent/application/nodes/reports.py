"""Узел Reports: собирает EmployeeReport, ProjectReport, ScreenshotTable + сохраняет."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date, timedelta

from work_activity_agent.application.services.evidence_builder import EvidenceBuilder
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    RiskLevel,
)
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.reports import (
    ActivityBreakdown,
    EmployeeReport,
    ProjectReport,
    ScreenshotTableRow,
)
from work_activity_agent.domain.models.risk import RiskFlag
from work_activity_agent.domain.models.screenshot import Screenshot
from work_activity_agent.infrastructure.observability.logging import get_logger

# Сколько минут "стоит" один скриншот для подсчёта breakdown.
# Дефолт; реальное значение берётся из settings.minutes_per_screenshot.
_MINUTES_PER_SCREENSHOT = 5


def make_reports_node(deps: Deps) -> Callable[[AgentState], AgentState]:
    log = get_logger("reports")
    evidence_builder = EvidenceBuilder()
    minutes_per_screenshot = deps.settings.minutes_per_screenshot

    def reports_node(state: AgentState) -> AgentState:
        log.info("reports.start", run_id=state.run_id)

        screenshots_by_id = {s.id: s for s in state.screenshots}

        # Собираем все RiskFlag'и (из patterns + relevance)
        all_flags = evidence_builder.build_flags(
            state.timeline_patterns, state.relevances, screenshots_by_id
        )

        # Группируем скрины по employee+date для дневных отчётов
        groups: dict[tuple[str, date], list[Screenshot]] = defaultdict(list)
        for s in state.screenshots:
            employee = s.metadata.employee_id or "_unknown"
            groups[(employee, s.captured_at.date())].append(s)

        employee_reports: list[EmployeeReport] = []
        for (employee_id, report_date), screenshots in groups.items():
            key = f"{employee_id}__{report_date.isoformat()}"
            risk_score = state.risk_scores.get(key)
            work_score = state.work_activity_scores.get(key)
            if not risk_score or not work_score:
                continue

            screenshot_id_set = {s.id for s in screenshots}
            employee_flags = tuple(
                f
                for f in all_flags
                if any(sid in screenshot_id_set for sid in f.screenshot_ids)
            )
            evidence_links = tuple(
                evidence_builder.build_evidence_links(employee_flags, screenshots_by_id)
            )

            breakdown = _build_breakdown(
                screenshots, state.classifications, minutes_per_screenshot
            )
            tracked_time = _compute_tracked_time(screenshots, minutes_per_screenshot)
            manager_summary = _build_manager_summary(
                employee_id, risk_score, work_score, employee_flags
            )

            employee_reports.append(
                EmployeeReport(
                    employee_id=employee_id,
                    date=report_date,
                    screenshots_total=len(screenshots),
                    tracked_time=tracked_time,
                    breakdown=breakdown,
                    risk_flags=employee_flags,
                    risk_score=risk_score,
                    work_activity_score=work_score,
                    manager_summary=manager_summary,
                    evidence_links=evidence_links,
                )
            )

        # Проектные отчёты — агрегаты по project_id
        project_reports = _build_project_reports(state.screenshots, state.classifications)

        # Screenshot table (ТЗ §15)
        screenshot_table = _build_screenshot_table(state, all_flags)

        # Запись через все sinks
        for sink in deps.report_sinks:
            for er in employee_reports:
                sink.write_employee_report(er)
            for pr in project_reports:
                sink.write_project_report(pr)
            sink.write_screenshot_table(screenshot_table)

        log.info(
            "reports.done",
            employee_reports=len(employee_reports),
            project_reports=len(project_reports),
            screenshot_table_rows=len(screenshot_table),
        )

        return state.model_copy(
            update={
                "employee_reports": employee_reports,
                "project_reports": project_reports,
                "screenshot_table": screenshot_table,
            }
        )

    return reports_node


def _build_breakdown(
    screenshots: list[Screenshot],
    classifications: dict[str, ClassificationResult],
    minutes_per_screenshot: int = _MINUTES_PER_SCREENSHOT,
) -> ActivityBreakdown:
    """Развёрстка по категориям: minutes_per_screenshot * count."""
    counts: dict[str, int] = defaultdict(int)
    for s in screenshots:
        cls = classifications.get(s.id)
        if cls:
            counts[cls.activity_type.value] += 1
        else:
            counts[ActivityType.NEUTRAL_UNCLEAR.value] += 1

    def minute_field(count: int) -> timedelta:
        return timedelta(minutes=count * minutes_per_screenshot)

    return ActivityBreakdown(
        productive_work=minute_field(counts.get(ActivityType.PRODUCTIVE_WORK.value, 0)),
        project_communication=minute_field(counts.get(ActivityType.PROJECT_COMMUNICATION.value, 0)),
        research=minute_field(counts.get(ActivityType.RESEARCH.value, 0)),
        admin_work=minute_field(counts.get(ActivityType.ADMIN_WORK.value, 0)),
        neutral_unclear=minute_field(counts.get(ActivityType.NEUTRAL_UNCLEAR.value, 0)),
        idle_static=minute_field(counts.get(ActivityType.IDLE_STATIC.value, 0)),
        non_work=minute_field(counts.get(ActivityType.NON_WORK.value, 0)),
        job_search_signal=minute_field(counts.get(ActivityType.JOB_SEARCH_SIGNAL.value, 0)),
        other_project_signal=minute_field(counts.get(ActivityType.OTHER_PROJECT_SIGNAL.value, 0)),
        sensitive_private=minute_field(counts.get(ActivityType.SENSITIVE_PRIVATE.value, 0)),
        needs_human_review=minute_field(counts.get(ActivityType.NEEDS_HUMAN_REVIEW.value, 0)),
    )


def _compute_tracked_time(
    screenshots: list[Screenshot],
    minutes_per_screenshot: int = _MINUTES_PER_SCREENSHOT,
) -> timedelta:
    total_minutes = sum((s.metadata.tracked_minutes or 0) for s in screenshots)
    if total_minutes > 0:
        return timedelta(minutes=total_minutes)
    return timedelta(minutes=len(screenshots) * minutes_per_screenshot)


def _build_manager_summary(
    employee_id: str,
    risk_score: object,
    work_score: object,
    flags: tuple[RiskFlag, ...],
) -> str:
    risk = getattr(risk_score, "score", 0)
    risk_level = getattr(getattr(risk_score, "level", None), "value", "low")
    work = getattr(work_score, "score", 0)
    work_level = getattr(getattr(work_score, "level", None), "value", "low")

    review_count = sum(1 for f in flags if f.requires_human_review)
    parts = [
        f"Сотрудник {employee_id}: risk_score={risk} ({risk_level}), "
        f"work_activity_score={work} ({work_level}).",
    ]
    if review_count > 0:
        parts.append(f"Обнаружено {review_count} эпизодов, требующих ручной проверки.")
    else:
        parts.append("Эпизодов, требующих проверки, не обнаружено.")
    return " ".join(parts)


def _build_project_reports(
    screenshots: list[Screenshot],
    classifications: dict[str, ClassificationResult],
) -> list[ProjectReport]:
    by_project: dict[str, list[Screenshot]] = defaultdict(list)
    for s in screenshots:
        if s.metadata.project_id:
            by_project[s.metadata.project_id].append(s)

    reports: list[ProjectReport] = []
    for project_id, items in by_project.items():
        n = len(items)
        if n == 0:
            continue
        productive = sum(
            1
            for s in items
            if (cls := classifications.get(s.id))
            and cls.activity_type
            in {
                ActivityType.PRODUCTIVE_WORK,
                ActivityType.RESEARCH,
                ActivityType.PROJECT_COMMUNICATION,
                ActivityType.ADMIN_WORK,
            }
        )
        unclear = sum(
            1
            for s in items
            if (cls := classifications.get(s.id))
            and cls.activity_type == ActivityType.NEUTRAL_UNCLEAR
        )
        non_work = sum(
            1
            for s in items
            if (cls := classifications.get(s.id))
            and cls.activity_type
            in {
                ActivityType.NON_WORK,
                ActivityType.JOB_SEARCH_SIGNAL,
                ActivityType.OTHER_PROJECT_SIGNAL,
            }
        )

        # Top tools — visible_application из vision_results, но мы здесь не имеем доступа
        # к ним — вместо этого используем app_hint из metadata
        tools_counter: Counter[str] = Counter(
            s.metadata.app_hint for s in items if s.metadata.app_hint
        )
        top_tools = tuple(name for name, _ in tools_counter.most_common(5))

        team = len({s.metadata.employee_id for s in items if s.metadata.employee_id})
        dates = [s.captured_at.date() for s in items]

        # n>0 здесь гарантировано выше через `if n == 0: continue`,
        # но дублируем guard локально — защищает от случайного рефакторинга.
        denom = n or 1
        reports.append(
            ProjectReport(
                project_id=project_id,
                period_start=min(dates),
                period_end=max(dates),
                team_members=team,
                screenshots_analyzed=n,
                productive_ratio=productive / denom,
                unclear_ratio=unclear / denom,
                non_work_ratio=non_work / denom,
                top_tools=top_tools,
            )
        )
    return reports


def _build_screenshot_table(
    state: AgentState,
    flags: list[RiskFlag],
) -> list[ScreenshotTableRow]:
    """Плоская таблица по каждому скриншоту (ТЗ §15)."""
    flags_by_screenshot: dict[str, list[str]] = defaultdict(list)
    for flag in flags:
        for sid in flag.screenshot_ids:
            flags_by_screenshot[sid].append(flag.type.value)

    rows: list[ScreenshotTableRow] = []
    for s in sorted(state.screenshots, key=lambda x: x.captured_at):
        cls = state.classifications.get(s.id)
        rel = state.relevances.get(s.id)
        if not cls:
            continue
        screenshot_flags = tuple(flags_by_screenshot.get(s.id, []))
        risk = _row_risk_level(cls.activity_type, rel.relevance if rel else None, screenshot_flags)
        rows.append(
            ScreenshotTableRow(
                time=s.captured_at.strftime("%H:%M"),
                employee=s.metadata.employee_id or "-",
                task=s.metadata.tracked_task_title or "-",
                summary=cls.evidence[0] if cls.evidence else cls.category,
                activity=cls.activity_type,
                relevance=rel.relevance if rel else RelevanceLevel.UNCLEAR,
                flags=screenshot_flags,
                risk=risk,
                review=bool(screenshot_flags),
            )
        )
    return rows


def _row_risk_level(
    activity: ActivityType,
    relevance: RelevanceLevel | None,
    flags: tuple[str, ...],
) -> RiskLevel:
    if not flags and activity in {
        ActivityType.PRODUCTIVE_WORK,
        ActivityType.RESEARCH,
        ActivityType.PROJECT_COMMUNICATION,
        ActivityType.ADMIN_WORK,
    }:
        return RiskLevel.LOW
    if activity in {ActivityType.JOB_SEARCH_SIGNAL, ActivityType.OTHER_PROJECT_SIGNAL}:
        return RiskLevel.HIGH
    if (
        activity in {ActivityType.NON_WORK, ActivityType.IDLE_STATIC}
        or relevance == RelevanceLevel.LOW
    ):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
