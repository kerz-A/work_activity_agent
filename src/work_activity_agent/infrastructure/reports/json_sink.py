"""JsonReportSink — запись отчётов в JSON файлы."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from work_activity_agent.domain.models.reports import (
    EmployeeReport,
    ProjectReport,
    ScreenshotTableRow,
)


class JsonReportSink:
    """Сохраняет отчёты как JSON файлы в `output_dir`.

    Структура:
        output_dir/
        ├── employee_<id>_<date>.json
        ├── project_<id>_<period>.json
        └── screenshots_table.json
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def write_employee_report(self, report: EmployeeReport) -> None:
        filename = f"employee_{report.employee_id}_{report.date.isoformat()}.json"
        path = self._output_dir / filename
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def write_project_report(self, report: ProjectReport) -> None:
        filename = (
            f"project_{report.project_id}_"
            f"{report.period_start.isoformat()}_{report.period_end.isoformat()}.json"
        )
        path = self._output_dir / filename
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def write_screenshot_table(self, rows: Sequence[ScreenshotTableRow]) -> None:
        path = self._output_dir / "screenshots_table.json"
        payload = [row.model_dump(mode="json") for row in rows]
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
