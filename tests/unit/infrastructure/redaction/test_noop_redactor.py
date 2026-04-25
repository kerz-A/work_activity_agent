"""Тесты NoopImageRedactor и NoopTextRedactor."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from work_activity_agent.domain.errors import RedactionError
from work_activity_agent.domain.models.screenshot import Screenshot
from work_activity_agent.infrastructure.redaction.noop_redactor import (
    NoopImageRedactor,
    NoopTextRedactor,
)


class TestNoopImageRedactor:
    def test_copies_file(self, tmp_path: Path) -> None:
        src = tmp_path / "a.png"
        src.write_bytes(b"image bytes")
        screenshot = Screenshot(
            id="scr_1",
            path=src,
            captured_at=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        )
        out = tmp_path / "out" / "a.redacted.png"
        result = NoopImageRedactor().redact(screenshot, out)
        assert out.exists()
        assert out.read_bytes() == b"image bytes"
        assert result.detected_types == ()
        assert result.bboxes_count == 0
        assert not result.has_pii

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        screenshot = Screenshot(
            id="scr_1",
            path=tmp_path / "missing.png",
            captured_at=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        )
        with pytest.raises(RedactionError, match="not found"):
            NoopImageRedactor().redact(screenshot, tmp_path / "out.png")


class TestNoopTextRedactor:
    def test_returns_unchanged(self) -> None:
        result, types = NoopTextRedactor().redact(["hello", "world"])
        assert result == ("hello", "world")
        assert types == ()
