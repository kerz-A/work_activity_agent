"""Порт ReportSink для записи отчётов (JSON, Markdown, в будущем Sheets/Slack)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from work_activity_agent.domain.models.reports import (
    EmployeeReport,
    ProjectReport,
    ScreenshotTableRow,
)


class ReportSink(Protocol):
    """Абстракция вывода отчётов.

    Реализации: `JsonReportSink`, `MarkdownReportSink`, `CsvReportSink`.
    """

    def write_employee_report(self, report: EmployeeReport) -> None:
        """Записать дневной отчёт по сотруднику."""
        ...

    def write_project_report(self, report: ProjectReport) -> None:
        """Записать проектный отчёт."""
        ...

    def write_screenshot_table(self, rows: Sequence[ScreenshotTableRow]) -> None:
        """Записать табличный вывод по скриншотам (формат ТЗ §15)."""
        ...
