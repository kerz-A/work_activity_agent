"""RegexTextRedactor — baseline маскировщик PII через регулярки.

Защитный слой ПОСЛЕ Vision на случай если Image Redactor что-то пропустил.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from work_activity_agent.domain.enums import SensitiveDataType

# Pattern → тип PII. Порядок важен: специфичные раньше общих.
_PATTERNS: tuple[tuple[re.Pattern[str], SensitiveDataType], ...] = (
    (
        re.compile(r"sk-[a-zA-Z0-9_-]{16,}", re.IGNORECASE),
        SensitiveDataType.TOKEN,
    ),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
        SensitiveDataType.PRIVATE_KEY,
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        SensitiveDataType.EMAIL,
    ),
    (
        # Международный формат: +дд-ддд-ддд-дддд или варианты со скобками/пробелами.
        # Минимум 7 цифр всего (исключая код страны), чтобы не матчить даты типа 2026-04-22.
        re.compile(
            r"(?:\+\d{1,3}[-\s.]?)"  # обязательный + и код страны
            r"(?:\(?\d{1,4}\)?[-\s.]?){2,4}"  # 2-4 группы цифр через разделитель
            r"\d{2,4}"  # хвост
        ),
        SensitiveDataType.PHONE,
    ),
    (
        # тестовая карта Visa и подобные — 13-19 цифр в группах
        re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4}\b"),
        SensitiveDataType.BANK_DETAILS,
    ),
    (
        # IBAN: страна + 2 цифры + 11-30 буквоцифр
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{11,30}\b"),
        SensitiveDataType.BANK_DETAILS,
    ),
)


class RegexTextRedactor:
    """Маскирует PII в массиве строк, заменяет на `[REDACTED:type]`."""

    def redact(
        self,
        texts: Sequence[str],
    ) -> tuple[tuple[str, ...], tuple[SensitiveDataType, ...]]:
        redacted: list[str] = []
        found: set[SensitiveDataType] = set()

        for text in texts:
            current = text
            for pattern, pii_type in _PATTERNS:
                if pattern.search(current):
                    found.add(pii_type)
                    current = pattern.sub(f"[REDACTED:{pii_type.value}]", current)
            redacted.append(current)

        return tuple(redacted), tuple(sorted(found, key=lambda t: t.value))
