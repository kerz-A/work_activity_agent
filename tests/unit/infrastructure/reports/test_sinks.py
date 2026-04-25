"""Тесты JsonReportSink и MarkdownReportSink."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

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
    ProjectReport,
    ScreenshotTableRow,
)
from work_activity_agent.domain.models.risk import RiskFlag, RiskScore, TimeInterval
from work_activity_agent.infrastructure.reports.json_sink import JsonReportSink
from work_activity_agent.infrastructure.reports.markdown_sink import MarkdownReportSink


@pytest.fixture
def employee_report() -> EmployeeReport:
    ts = datetime(2026, 4, 22, 14, 20, 0, tzinfo=UTC)
    return EmployeeReport(
        employee_id="emp_12",
        date=date(2026, 4, 22),
        screenshots_total=96,
        tracked_time=timedelta(hours=8),
        breakdown=ActivityBreakdown(productive_work=timedelta(hours=5, minutes=45)),
        risk_flags=(
            RiskFlag(
                type=RiskFlagType.STATIC_SCREEN_LONG_PERIOD,
                interval=TimeInterval(start=ts, end=ts + timedelta(minutes=30)),
                severity=RiskLevel.MEDIUM,
                evidence="6 похожих скринов подряд",
                screenshot_ids=("scr_1",),
                requires_human_review=True,
            ),
        ),
        risk_score=RiskScore(
            employee_id="emp_12",
            date=date(2026, 4, 22),
            score=42,
            level=RiskLevel.MEDIUM,
            components={"static_ratio": 0.21},
            summary="Умеренный риск",
            recommended_action="Проверка с менеджером",
        ),
        work_activity_score=WorkActivityScore(
            employee_id="emp_12",
            date=date(2026, 4, 22),
            score=70,
            level=WorkActivityLevel.HIGH,
            components=ActivityComponents(task_alignment=0.85),
        ),
        manager_summary="Большая часть активности соответствует задачам",
    )


@pytest.fixture
def project_report() -> ProjectReport:
    return ProjectReport(
        project_id="client_mobile",
        period_start=date(2026, 4, 15),
        period_end=date(2026, 4, 22),
        team_members=5,
        screenshots_analyzed=2140,
        productive_ratio=0.76,
        unclear_ratio=0.13,
        non_work_ratio=0.04,
        top_tools=("Figma", "VS Code"),
        project_risks=("Static intervals 30+ min",),
        recommendations=("Уточнить правила трекинга",),
    )


@pytest.fixture
def screenshot_rows() -> list[ScreenshotTableRow]:
    return [
        ScreenshotTableRow(
            time="10:00",
            employee="dev_1",
            task="auth bug",
            summary="VS Code",
            activity=ActivityType.PRODUCTIVE_WORK,
            relevance=RelevanceLevel.HIGH,
            risk=RiskLevel.LOW,
            review=False,
        ),
        ScreenshotTableRow(
            time="16:10",
            employee="dev_1",
            task="auth bug",
            summary="hh.ru",
            activity=ActivityType.JOB_SEARCH_SIGNAL,
            relevance=RelevanceLevel.LOW,
            flags=("job_search_site",),
            risk=RiskLevel.HIGH,
            review=True,
        ),
    ]


class TestJsonReportSink:
    def test_writes_employee_report(self, tmp_path: Path, employee_report: EmployeeReport) -> None:
        sink = JsonReportSink(tmp_path)
        sink.write_employee_report(employee_report)
        f = tmp_path / "employee_emp_12_2026-04-22.json"
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["employee_id"] == "emp_12"
        assert data["risk_score"]["score"] == 42
        assert data["work_activity_score"]["score"] == 70

    def test_writes_project_report(self, tmp_path: Path, project_report: ProjectReport) -> None:
        sink = JsonReportSink(tmp_path)
        sink.write_project_report(project_report)
        files = list(tmp_path.glob("project_client_mobile_*.json"))
        assert len(files) == 1

    def test_writes_screenshot_table(
        self, tmp_path: Path, screenshot_rows: list[ScreenshotTableRow]
    ) -> None:
        sink = JsonReportSink(tmp_path)
        sink.write_screenshot_table(screenshot_rows)
        f = tmp_path / "screenshots_table.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[1]["activity"] == "job_search_signal"


class TestMarkdownReportSink:
    def test_employee_report_md(self, tmp_path: Path, employee_report: EmployeeReport) -> None:
        MarkdownReportSink(tmp_path).write_employee_report(employee_report)
        f = tmp_path / "employee_emp_12_2026-04-22.md"
        text = f.read_text(encoding="utf-8")
        assert "Risk Score" in text
        assert "42" in text
        assert "Work Activity Score" in text
        assert "static_screen_long_period" in text
        assert "REVIEW" in text  # маркер требуется проверка

    def test_project_report_md(self, tmp_path: Path, project_report: ProjectReport) -> None:
        MarkdownReportSink(tmp_path).write_project_report(project_report)
        files = list(tmp_path.glob("project_*.md"))
        assert len(files) == 1
        text = files[0].read_text(encoding="utf-8")
        assert "76.0%" in text
        assert "Figma" in text

    def test_screenshot_table_md_format(
        self, tmp_path: Path, screenshot_rows: list[ScreenshotTableRow]
    ) -> None:
        MarkdownReportSink(tmp_path).write_screenshot_table(screenshot_rows)
        f = tmp_path / "screenshots_table.md"
        text = f.read_text(encoding="utf-8")
        # Заголовок ТЗ §15
        assert "Time" in text
        assert "Activity" in text
        assert "Relevance" in text
        # Контент
        assert "10:00" in text
        assert "16:10" in text
        assert "Yes" in text
        assert "No" in text
