"""Порт TextRedactor — защитный слой ПОСЛЕ Vision на случай если Image redaction что-то пропустил."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from work_activity_agent.domain.enums import SensitiveDataType


class TextRedactor(Protocol):
    """Маскирует PII в текстовом выходе Vision (`visible_text`).

    Реализации: `RegexTextRedactor` (regex baseline), `PresidioTextRedactor` (Presidio Analyzer).
    """

    def redact(
        self,
        texts: Sequence[str],
    ) -> tuple[tuple[str, ...], tuple[SensitiveDataType, ...]]:
        """Прогнать тексты через анализатор PII, заменить найденное на токены `[REDACTED:type]`.

        :param texts: входные строки
        :return: (маскированные строки, найденные типы)
        """
        ...
