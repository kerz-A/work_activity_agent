"""Protocol-порты для зависимостей. Реализации — в infrastructure/."""

from work_activity_agent.domain.ports.image_redactor import ImageRedactor
from work_activity_agent.domain.ports.llm_provider import LLMProvider
from work_activity_agent.domain.ports.manifest_loader import ManifestLoader
from work_activity_agent.domain.ports.prompt_loader import PromptLoader, PromptTemplate
from work_activity_agent.domain.ports.report_sink import ReportSink
from work_activity_agent.domain.ports.storage import ScreenshotStorage
from work_activity_agent.domain.ports.text_redactor import TextRedactor

__all__ = [
    "ImageRedactor",
    "LLMProvider",
    "ManifestLoader",
    "PromptLoader",
    "PromptTemplate",
    "ReportSink",
    "ScreenshotStorage",
    "TextRedactor",
]
