"""Тесты structlog setup."""

import io
import json
import sys

import pytest
import structlog

from work_activity_agent.config.settings import ObservabilitySettings
from work_activity_agent.infrastructure.observability.logging import (
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    """Сбрасывает конфиг structlog после каждого теста — чтобы тесты были изолированы."""
    yield
    structlog.reset_defaults()


class TestConfigureLogging:
    def test_json_output(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Перенаправляем stderr в буфер
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)

        configure_logging(ObservabilitySettings(json_logs=True, log_level="INFO"))
        log = get_logger("test")
        log.info("hello", foo="bar", count=42)

        output = buf.getvalue().strip()
        assert output  # something was logged
        parsed = json.loads(output)
        assert parsed["event"] == "hello"
        assert parsed["foo"] == "bar"
        assert parsed["count"] == 42
        assert parsed["level"] == "info"
        assert "timestamp" in parsed

    def test_console_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)

        configure_logging(ObservabilitySettings(json_logs=False, log_level="INFO"))
        log = get_logger("test")
        log.info("hello", foo="bar")

        output = buf.getvalue()
        assert "hello" in output
        assert "foo" in output

    def test_log_level_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)

        configure_logging(ObservabilitySettings(json_logs=True, log_level="WARNING"))
        log = get_logger("test")
        log.debug("not visible")
        log.info("not visible either")
        log.warning("visible")

        output = buf.getvalue()
        assert "not visible" not in output
        assert "visible" in output


class TestGetLogger:
    def test_get_logger_no_context(self) -> None:
        configure_logging(ObservabilitySettings())
        log = get_logger("test")
        assert log is not None

    def test_get_logger_with_initial_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)

        configure_logging(ObservabilitySettings(json_logs=True))
        log = get_logger("vision", run_id="abc123", node="vision")
        log.info("vision.start")

        parsed = json.loads(buf.getvalue().strip())
        assert parsed["run_id"] == "abc123"
        assert parsed["node"] == "vision"
