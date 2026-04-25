"""Тесты что Protocol-порты импортируются и используются как протоколы.

Сами реализации тестируются в tests/unit/infrastructure/.
"""

from work_activity_agent.domain.ports import (
    ImageRedactor,
    LLMProvider,
    ManifestLoader,
    PromptLoader,
    PromptTemplate,
    ReportSink,
    ScreenshotStorage,
    TextRedactor,
)


class TestPortsImportable:
    def test_all_ports_present(self) -> None:
        for port in (
            LLMProvider,
            ImageRedactor,
            TextRedactor,
            ScreenshotStorage,
            ManifestLoader,
            ReportSink,
            PromptLoader,
        ):
            assert port is not None


class TestPromptTemplate:
    def test_valid(self) -> None:
        t = PromptTemplate(
            name="vision_describe",
            version="1.0.0",
            model_alias="vision_primary",
            content="Hello {{ name }}",
        )
        assert t.render(name="world") == "Hello world"

    def test_invalid_version_format_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError as PydValidationError

        with pytest.raises(PydValidationError):
            PromptTemplate(
                name="x",
                version="not-semver",
                model_alias="vp",
                content="x",
            )
