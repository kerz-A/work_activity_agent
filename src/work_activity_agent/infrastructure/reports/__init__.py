"""Адаптеры записи отчётов."""

from work_activity_agent.infrastructure.reports.json_sink import JsonReportSink
from work_activity_agent.infrastructure.reports.markdown_sink import MarkdownReportSink

__all__ = ["JsonReportSink", "MarkdownReportSink"]
