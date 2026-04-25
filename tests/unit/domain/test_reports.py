"""Тесты EmployeeReport, ProjectReport, ScreenshotTableRow, ActivityBreakdown."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    RiskFlagType,
    RiskLevel,
    WorkActivityLevel,
)
from work_activity_agent.domain.models.productivity import (
    ActivityComponents,
    WorkActivityScore,
)
from work_activity_agent.domain.models.reports import (
    ActivityBreakdown,
    EmployeeReport,
    EvidenceLink,
    ProjectReport,
    ScreenshotTableRow,
)
from work_activity_agent.domain.models.risk import (
    RiskFlag,
    RiskScore,
    TimeInterval,
)


class TestActivityBreakdown:
    def test_default_zeros(self) -> None:
        b = ActivityBreakdown()
        assert b.total == timedelta(0)

    def test_total_sums_all_categories(self) -> None:
        b = ActivityBreakdown(
            productive_work=timedelta(hours=5, minutes=45),
            project_communication=timedelta(minutes=45),
            research=timedelta(minutes=35),
            neutral_unclear=timedelta(minutes=25),
            non_work=timedelta(minutes=10),
        )
        assert b.total == timedelta(hours=7, minutes=40)


class TestEvidenceLink:
    def test_valid(self) -> None:
        link = EvidenceLink(
            screenshot_id="scr_1",
            path=Path("fixtures/screenshots/productive/scr_1.png"),
            caption="VS Code, payment service",
        )
        assert link.screenshot_id == "scr_1"

    def test_empty_caption_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceLink(
                screenshot_id="scr_1",
                path=Path("a.png"),
                caption="",
            )


class TestScreenshotTableRow:
    def test_valid(self) -> None:
        row = ScreenshotTableRow(
            time="10:00",
            employee="dev_1",
            task="auth bug",
            summary="VS Code, auth middleware",
            activity=ActivityType.PRODUCTIVE_WORK,
            relevance=RelevanceLevel.HIGH,
            risk=RiskLevel.LOW,
            review=False,
        )
        assert row.flags == ()

    def test_with_flags(self) -> None:
        row = ScreenshotTableRow(
            time="11:20",
            employee="dev_1",
            task="auth bug",
            summary="YouTube",
            activity=ActivityType.NON_WORK,
            relevance=RelevanceLevel.LOW,
            flags=("entertainment_content",),
            risk=RiskLevel.MEDIUM,
            review=True,
        )
        assert row.review


class TestEmployeeReport:
    def _build(self) -> EmployeeReport:
        ts = datetime(2026, 4, 22, 14, 20, 0, tzinfo=UTC)
        risk_flag = RiskFlag(
            type=RiskFlagType.STATIC_SCREEN_LONG_PERIOD,
            interval=TimeInterval(start=ts, end=ts + timedelta(minutes=30)),
            severity=RiskLevel.MEDIUM,
            evidence="6 похожих скриншотов",
            screenshot_ids=("scr_1",),
        )
        risk_score = RiskScore(
            employee_id="emp_12",
            date=date(2026, 4, 22),
            score=42,
            level=RiskLevel.MEDIUM,
            components={"static_ratio": 0.21},
            summary="Умеренный риск",
            recommended_action="Проверка с менеджером",
        )
        wa_score = WorkActivityScore(
            employee_id="emp_12",
            date=date(2026, 4, 22),
            score=70,
            level=WorkActivityLevel.HIGH,
            components=ActivityComponents(task_alignment=0.85),
        )
        return EmployeeReport(
            employee_id="emp_12",
            date=date(2026, 4, 22),
            screenshots_total=96,
            tracked_time=timedelta(hours=8),
            breakdown=ActivityBreakdown(
                productive_work=timedelta(hours=5, minutes=45),
            ),
            risk_flags=(risk_flag,),
            risk_score=risk_score,
            work_activity_score=wa_score,
            manager_summary="Большая часть активности соответствует задачам",
        )

    def test_full_report_compiles(self) -> None:
        report = self._build()
        assert report.screenshots_total == 96
        assert report.risk_score.score == 42
        assert report.work_activity_score.score == 70


class TestProjectReport:
    def test_valid(self) -> None:
        r = ProjectReport(
            project_id="client_mobile",
            period_start=date(2026, 4, 15),
            period_end=date(2026, 4, 22),
            team_members=5,
            screenshots_analyzed=2140,
            productive_ratio=0.76,
            unclear_ratio=0.13,
            non_work_ratio=0.04,
            top_tools=("Figma", "VS Code", "GitHub"),
        )
        assert r.team_members == 5

    def test_ratios_in_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            ProjectReport(
                project_id="x",
                period_start=date(2026, 4, 1),
                period_end=date(2026, 4, 7),
                team_members=1,
                screenshots_analyzed=10,
                productive_ratio=1.5,
                unclear_ratio=0.0,
                non_work_ratio=0.0,
            )
