"""MarkdownReportSink — запись отчётов как Markdown.

Включает screenshot_table.md формата ТЗ §15.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from work_activity_agent.domain.models.reports import (
    EmployeeReport,
    ProjectReport,
    ScreenshotTableRow,
)


class MarkdownReportSink:
    """Сохраняет отчёты как читабельный Markdown."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def write_employee_report(self, report: EmployeeReport) -> None:
        filename = f"employee_{report.employee_id}_{report.date.isoformat()}.md"
        path = self._output_dir / filename
        lines = [
            f"# Дневной отчёт — {report.employee_id} — {report.date.isoformat()}",
            "",
            f"- Скриншотов всего: **{report.screenshots_total}**",
            f"- Трекнутое время: **{report.tracked_time}**",
            "",
            "## Risk Score",
            f"- **{report.risk_score.score}** ({report.risk_score.level.value})",
            f"- {report.risk_score.summary}",
            f"- Рекомендация: {report.risk_score.recommended_action}",
            "",
            "## Work Activity Score",
            f"- **{report.work_activity_score.score}** ({report.work_activity_score.level.value})",
        ]
        if report.work_activity_score.note:
            lines.append(f"- Заметка: {report.work_activity_score.note}")

        if report.risk_flags:
            lines.extend(["", "## Risk flags"])
            for flag in report.risk_flags:
                review_marker = " 🔴 REVIEW" if flag.requires_human_review else ""
                lines.append(
                    f"- **{flag.type.value}** [{flag.severity.value}]"
                    f" {flag.interval.start.strftime('%H:%M')}-"
                    f"{flag.interval.end.strftime('%H:%M')}{review_marker}: {flag.evidence}"
                )

        lines.extend(["", "## Резюме менеджеру", report.manager_summary])

        if report.evidence_links:
            lines.extend(["", "## Доказательства"])
            for link in report.evidence_links:
                lines.append(f"- [{link.caption}]({link.path}) ({link.screenshot_id})")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_project_report(self, report: ProjectReport) -> None:
        filename = (
            f"project_{report.project_id}_"
            f"{report.period_start.isoformat()}_{report.period_end.isoformat()}.md"
        )
        path = self._output_dir / filename
        lines = [
            f"# Проектный отчёт — {report.project_id}",
            f"Период: {report.period_start.isoformat()} — {report.period_end.isoformat()}",
            "",
            f"- Команда: {report.team_members} человек",
            f"- Скриншотов проанализировано: {report.screenshots_analyzed}",
            f"- Productive ratio: {report.productive_ratio:.1%}",
            f"- Unclear ratio: {report.unclear_ratio:.1%}",
            f"- Non-work ratio: {report.non_work_ratio:.1%}",
        ]
        if report.top_tools:
            lines.extend(["", "## Топ инструменты"])
            for t in report.top_tools:
                lines.append(f"- {t}")
        if report.project_risks:
            lines.extend(["", "## Риски проекта"])
            for r in report.project_risks:
                lines.append(f"- {r}")
        if report.recommendations:
            lines.extend(["", "## Рекомендации"])
            for rec in report.recommendations:
                lines.append(f"- {rec}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_screenshot_table(self, rows: Sequence[ScreenshotTableRow]) -> None:
        """Таблица формата ТЗ §15: Time | Employee | Task | Summary | Activity | Relevance | Flags | Risk | Review."""
        path = self._output_dir / "screenshots_table.md"
        header = (
            "| Time | Employee | Task | Summary | Activity | Relevance | Flags | Risk | Review |"
        )
        sep = "|------|----------|------|---------|----------|-----------|-------|------|--------|"
        lines = [header, sep]
        for row in rows:
            flags_str = ", ".join(row.flags) if row.flags else "—"
            review_str = "Yes" if row.review else "No"
            lines.append(
                f"| {row.time} | {row.employee} | {row.task} | {row.summary} | "
                f"{row.activity.value} | {row.relevance.value} | {flags_str} | "
                f"{row.risk.value} | {review_str} |"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
