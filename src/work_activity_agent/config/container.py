"""DI container — собирает все зависимости в единый Deps dataclass.

Используется при сборке LangGraph: `build_graph(deps)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from work_activity_agent.config.settings import Settings
from work_activity_agent.domain.ports import (
    ImageRedactor,
    LLMProvider,
    ManifestLoader,
    PromptLoader,
    ReportSink,
    ScreenshotStorage,
    TextRedactor,
)


@dataclass(frozen=True)
class Deps:
    """Контейнер всех зависимостей агента."""

    settings: Settings
    llm: LLMProvider
    image_redactor: ImageRedactor
    text_redactor: TextRedactor
    storage: ScreenshotStorage
    manifest_loader: ManifestLoader
    report_sinks: tuple[ReportSink, ...]
    prompt_loader: PromptLoader


def build_dependencies(
    settings: Settings | None = None,
    *,
    use_fake_llm: bool = False,
    use_noop_redactor: bool = False,
) -> Deps:
    """Собрать продакшн Deps.

    :param settings: настройки (по умолчанию Settings() — берёт из env/.env)
    :param use_fake_llm: использовать FakeLLMProvider (для dry-run)
    :param use_noop_redactor: использовать NoopImageRedactor (для dry-run без Tesseract)
    """
    from work_activity_agent.infrastructure.llm.fake_provider import FakeLLMProvider
    from work_activity_agent.infrastructure.observability.logging import configure_logging
    from work_activity_agent.infrastructure.prompts.filesystem_loader import (
        FilesystemPromptLoader,
    )
    from work_activity_agent.infrastructure.redaction.noop_redactor import (
        NoopImageRedactor,
    )
    from work_activity_agent.infrastructure.redaction.regex_text_redactor import (
        RegexTextRedactor,
    )
    from work_activity_agent.infrastructure.reports.json_sink import JsonReportSink
    from work_activity_agent.infrastructure.reports.markdown_sink import MarkdownReportSink
    from work_activity_agent.infrastructure.storage.local_fs import LocalFSStorage
    from work_activity_agent.infrastructure.storage.manifest_yaml import YamlManifestLoader

    if settings is None:
        settings = Settings()

    configure_logging(settings.observability)

    llm: LLMProvider
    if use_fake_llm:
        llm = FakeLLMProvider()
    else:
        from work_activity_agent.infrastructure.llm.litellm_provider import LiteLLMProvider

        llm = LiteLLMProvider(settings.llm)

    image_redactor: ImageRedactor
    if use_noop_redactor:
        image_redactor = NoopImageRedactor()
    else:
        from work_activity_agent.infrastructure.redaction.presidio_image_redactor import (
            PresidioImageRedactor,
        )

        image_redactor = PresidioImageRedactor()

    return Deps(
        settings=settings,
        llm=llm,
        image_redactor=image_redactor,
        text_redactor=RegexTextRedactor(),
        storage=LocalFSStorage(),
        manifest_loader=YamlManifestLoader(),
        report_sinks=(
            JsonReportSink(settings.output_dir),
            MarkdownReportSink(settings.output_dir),
        ),
        prompt_loader=FilesystemPromptLoader(Path("configs/prompts")),
    )
