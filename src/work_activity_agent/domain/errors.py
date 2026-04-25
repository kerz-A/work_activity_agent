"""Доменные исключения. Узкие, не голый Exception."""


class DomainError(Exception):
    """Базовое исключение домена."""


class InvalidScreenshotMetadataError(DomainError):
    """Метаданные скриншота противоречивы или невалидны."""


class InvalidTimeIntervalError(DomainError):
    """Конец интервала раньше начала."""


class PromptNotFoundError(DomainError):
    """Запрошенный промпт не найден в реестре."""

    def __init__(self, name: str, version: str | None = None) -> None:
        msg = f"prompt '{name}'"
        if version is not None:
            msg += f" version '{version}'"
        msg += " not found"
        super().__init__(msg)
        self.name = name
        self.version = version


class ManifestParseError(DomainError):
    """Manifest.yaml не парсится или невалиден."""


class LLMResponseValidationError(DomainError):
    """LLM вернул ответ, не соответствующий ожидаемой Pydantic-схеме."""

    def __init__(self, schema_name: str, raw_response: str, *, attempt: int = 1) -> None:
        super().__init__(
            f"LLM response failed validation against {schema_name} (attempt {attempt}): "
            f"{raw_response[:200]}"
        )
        self.schema_name = schema_name
        self.raw_response = raw_response
        self.attempt = attempt


class RedactionError(DomainError):
    """Ошибка при работе redactor'а."""


class StorageError(DomainError):
    """Ошибка чтения/записи скриншотов или отчётов."""
