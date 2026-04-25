"""Тесты доменных исключений: иерархия и сообщения."""

import pytest

from work_activity_agent.domain.errors import (
    DomainError,
    InvalidScreenshotMetadataError,
    InvalidTimeIntervalError,
    LLMResponseValidationError,
    ManifestParseError,
    PromptNotFoundError,
    RedactionError,
    StorageError,
)


class TestErrorHierarchy:
    def test_all_inherit_from_domain_error(self) -> None:
        for cls in (
            InvalidScreenshotMetadataError,
            InvalidTimeIntervalError,
            PromptNotFoundError,
            ManifestParseError,
            LLMResponseValidationError,
            RedactionError,
            StorageError,
        ):
            assert issubclass(cls, DomainError)


class TestPromptNotFoundError:
    def test_message_contains_name(self) -> None:
        with pytest.raises(PromptNotFoundError) as exc_info:
            raise PromptNotFoundError("vision_describe")
        assert "vision_describe" in str(exc_info.value)
        assert exc_info.value.name == "vision_describe"
        assert exc_info.value.version is None

    def test_message_contains_version_when_provided(self) -> None:
        err = PromptNotFoundError("vision_describe", version="2.0.0")
        assert "2.0.0" in str(err)


class TestLLMResponseValidationError:
    def test_truncates_long_response(self) -> None:
        long_response = "x" * 1000
        err = LLMResponseValidationError("VisionResult", long_response, attempt=2)
        assert "VisionResult" in str(err)
        assert "attempt 2" in str(err)
        assert len(str(err)) < 500
