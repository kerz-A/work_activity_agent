"""Тесты RegexTextRedactor."""

import pytest

from work_activity_agent.domain.enums import SensitiveDataType
from work_activity_agent.infrastructure.redaction.regex_text_redactor import (
    RegexTextRedactor,
)


@pytest.fixture
def redactor() -> RegexTextRedactor:
    return RegexTextRedactor()


class TestEmailDetection:
    def test_detects_basic_email(self, redactor: RegexTextRedactor) -> None:
        texts = ("Contact: test@example.com",)
        result, types = redactor.redact(texts)
        assert "[REDACTED:email]" in result[0]
        assert "test@example.com" not in result[0]
        assert SensitiveDataType.EMAIL in types

    def test_detects_multiple_emails(self, redactor: RegexTextRedactor) -> None:
        texts = ("a@b.com and c@d.io",)
        result, _ = redactor.redact(texts)
        assert result[0].count("[REDACTED:email]") == 2


class TestPhoneDetection:
    def test_detects_international_phone(self, redactor: RegexTextRedactor) -> None:
        texts = ("Call +7-000-000-0000",)
        result, types = redactor.redact(texts)
        assert "[REDACTED:phone]" in result[0]
        assert SensitiveDataType.PHONE in types

    def test_detects_us_phone(self, redactor: RegexTextRedactor) -> None:
        texts = ("Call +1-555-0100",)
        result, types = redactor.redact(texts)
        assert "[REDACTED:phone]" in result[0]
        assert SensitiveDataType.PHONE in types


class TestTokenDetection:
    def test_detects_sk_token(self, redactor: RegexTextRedactor) -> None:
        texts = ("Token: sk-test-abcdefghijklmnop1234",)
        result, types = redactor.redact(texts)
        assert "[REDACTED:token]" in result[0]
        assert "sk-test" not in result[0]
        assert SensitiveDataType.TOKEN in types


class TestBankDetection:
    def test_detects_credit_card(self, redactor: RegexTextRedactor) -> None:
        texts = ("Card: 4111-1111-1111-1111",)
        result, types = redactor.redact(texts)
        assert "[REDACTED:bank_details]" in result[0]
        assert SensitiveDataType.BANK_DETAILS in types

    def test_detects_iban(self, redactor: RegexTextRedactor) -> None:
        texts = ("IBAN: DE89370400440532013000",)
        result, _types = redactor.redact(texts)
        assert "[REDACTED:bank_details]" in result[0]


class TestPrivateKeyDetection:
    def test_detects_private_key_block(self, redactor: RegexTextRedactor) -> None:
        texts = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA...truncated...\n"
            "-----END RSA PRIVATE KEY-----",
        )
        result, types = redactor.redact(texts)
        assert "[REDACTED:private_key]" in result[0]
        assert "MIIEpAIBAAKCAQEA" not in result[0]
        assert SensitiveDataType.PRIVATE_KEY in types


class TestNoFindings:
    def test_clean_text_unchanged(self, redactor: RegexTextRedactor) -> None:
        texts = ("Hello world", "fix payment retry")
        result, types = redactor.redact(texts)
        assert result == texts
        assert types == ()
