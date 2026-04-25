"""Тесты VisionResult, RedactionResult, ExtractedMetadata."""

import pytest
from pydantic import ValidationError

from work_activity_agent.domain.enums import RedactionAction, SensitiveDataType
from work_activity_agent.domain.models.vision import (
    ExtractedMetadata,
    RedactionResult,
    VisionResult,
)


class TestVisionResult:
    def _valid(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "screenshot_id": "scr_1",
            "visible_application": "VS Code",
            "interpreted_activity": "editing payment.service.ts",
            "confidence": 0.85,
            "model_used": "anthropic/claude-sonnet-4-5",
        }
        base.update(overrides)
        return base

    def test_minimal_valid(self) -> None:
        r = VisionResult(**self._valid())  # type: ignore[arg-type]
        assert r.visible_application == "VS Code"
        assert r.visible_text == ()

    def test_confidence_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError):
            VisionResult(**self._valid(confidence=1.1))  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            VisionResult(**self._valid(confidence=-0.1))  # type: ignore[arg-type]

    def test_visible_text_capped_at_20(self) -> None:
        with pytest.raises(ValidationError):
            VisionResult(  # type: ignore[arg-type]
                **self._valid(visible_text=tuple(f"line {i}" for i in range(21)))
            )


class TestRedactionResult:
    def test_default_action_is_mask(self) -> None:
        r = RedactionResult(screenshot_id="scr_1")
        assert r.action == RedactionAction.MASK_BEFORE_REPORT
        assert not r.has_findings

    def test_has_findings_when_types_present(self) -> None:
        r = RedactionResult(
            screenshot_id="scr_1",
            detected_types=(SensitiveDataType.EMAIL, SensitiveDataType.PHONE),
        )
        assert r.has_findings


class TestExtractedMetadata:
    def test_empty_default(self) -> None:
        m = ExtractedMetadata()
        assert m.employee_hint is None
