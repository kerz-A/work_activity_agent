"""Тесты Screenshot, ScreenshotMetadata, RedactedScreenshot."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from work_activity_agent.domain.enums import SensitiveDataType
from work_activity_agent.domain.models.screenshot import (
    RedactedScreenshot,
    Screenshot,
    ScreenshotMetadata,
)


class TestScreenshotMetadata:
    def test_all_fields_optional_default_none(self) -> None:
        meta = ScreenshotMetadata()
        assert meta.employee_id is None
        assert meta.tracked_minutes is None

    def test_negative_tracked_minutes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotMetadata(tracked_minutes=-1)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotMetadata(unknown_field="x")  # type: ignore[call-arg]

    def test_immutable(self) -> None:
        meta = ScreenshotMetadata(employee_id="dev_1")
        with pytest.raises(ValidationError):
            meta.employee_id = "other"  # type: ignore[misc]


class TestScreenshot:
    def _ts(self) -> datetime:
        return datetime(2026, 4, 22, 10, 15, 0, tzinfo=UTC)

    def test_minimal_screenshot(self) -> None:
        s = Screenshot(id="scr_1", path=Path("a.png"), captured_at=self._ts())
        assert s.id == "scr_1"
        assert s.metadata == ScreenshotMetadata()

    def test_naive_datetime_rejected(self) -> None:
        naive = datetime(2026, 4, 22, 10, 15, 0)
        with pytest.raises(ValidationError):
            Screenshot(id="scr_1", path=Path("a.png"), captured_at=naive)

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Screenshot(id="", path=Path("a.png"), captured_at=self._ts())


class TestRedactedScreenshot:
    def _screenshot(self) -> Screenshot:
        return Screenshot(
            id="scr_1",
            path=Path("a.png"),
            captured_at=datetime(2026, 4, 22, 10, 15, 0, tzinfo=UTC),
        )

    def test_no_pii_by_default(self) -> None:
        rs = RedactedScreenshot(
            original=self._screenshot(),
            redacted_path=Path("a.redacted.png"),
        )
        assert not rs.has_pii
        assert rs.detected_types == ()

    def test_has_pii_when_bboxes_positive(self) -> None:
        rs = RedactedScreenshot(
            original=self._screenshot(),
            redacted_path=Path("a.redacted.png"),
            detected_types=(SensitiveDataType.EMAIL,),
            bboxes_count=2,
        )
        assert rs.has_pii

    def test_negative_bboxes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RedactedScreenshot(
                original=self._screenshot(),
                redacted_path=Path("a.redacted.png"),
                bboxes_count=-1,
            )
