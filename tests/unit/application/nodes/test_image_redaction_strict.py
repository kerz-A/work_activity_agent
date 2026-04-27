"""Тесты privacy_strict mode в image_redaction node."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from work_activity_agent.application.nodes.image_redaction import make_image_redaction_node
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.errors import RedactionError
from work_activity_agent.domain.models.screenshot import (
    RedactedScreenshot,
    Screenshot,
    ScreenshotMetadata,
)


class _FailingRedactor:
    """Image redactor который всегда поднимает RedactionError."""

    def redact(self, screenshot: Screenshot, output_path: Path) -> RedactedScreenshot:
        raise RedactionError("simulated tesseract not found")


@pytest.fixture
def state_with_one_screenshot(tmp_path: Path) -> AgentState:
    file_path = tmp_path / "shot.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    screenshot = Screenshot(
        id="shot",
        path=file_path,
        captured_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
        metadata=ScreenshotMetadata(employee_id="dev_1"),
    )
    return AgentState(input_dir=tmp_path, screenshots=[screenshot])


def test_strict_mode_drops_screenshot_on_redaction_failure(
    test_deps: Deps, state_with_one_screenshot: AgentState
) -> None:
    """privacy_strict=True: скрин не попадает в redacted_screenshots, есть NodeError."""
    deps = Deps(
        settings=test_deps.settings.model_copy(
            update={"llm": test_deps.settings.llm.model_copy(update={"privacy_strict": True})}
        ),
        llm=test_deps.llm,
        image_redactor=_FailingRedactor(),
        text_redactor=test_deps.text_redactor,
        storage=test_deps.storage,
        manifest_loader=test_deps.manifest_loader,
        report_sinks=test_deps.report_sinks,
        prompt_loader=test_deps.prompt_loader,
    )
    node = make_image_redaction_node(deps)
    result = node(state_with_one_screenshot)

    assert result.redacted_screenshots == {}
    assert len(result.errors) == 1
    assert result.errors[0].node == "image_redaction"
    assert "privacy_strict=True" in result.errors[0].message


def test_lax_mode_falls_back_to_original_on_redaction_failure(
    test_deps: Deps, state_with_one_screenshot: AgentState
) -> None:
    """privacy_strict=False: скрин с оригиналом попадает в Vision, NodeError фиксируется."""
    deps = Deps(
        settings=test_deps.settings.model_copy(
            update={"llm": test_deps.settings.llm.model_copy(update={"privacy_strict": False})}
        ),
        llm=test_deps.llm,
        image_redactor=_FailingRedactor(),
        text_redactor=test_deps.text_redactor,
        storage=test_deps.storage,
        manifest_loader=test_deps.manifest_loader,
        report_sinks=test_deps.report_sinks,
        prompt_loader=test_deps.prompt_loader,
    )
    node = make_image_redaction_node(deps)
    result = node(state_with_one_screenshot)

    assert "shot" in result.redacted_screenshots
    assert (
        result.redacted_screenshots["shot"].redacted_path
        == state_with_one_screenshot.screenshots[0].path
    )
    assert len(result.errors) == 1
    assert "using original" in result.errors[0].message
