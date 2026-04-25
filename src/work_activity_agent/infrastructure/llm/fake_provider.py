"""FakeLLMProvider — детерминистичная замена LLM для тестов и dry-run.

Возвращает заранее записанные JSON-ответы по ключу. Не делает реальных API-вызовов.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from work_activity_agent.domain.errors import LLMResponseValidationError

T = TypeVar("T", bound=BaseModel)


class FakeLLMProvider:
    """In-memory детерминистичный LLM.

    Использование:
        # 1. Через словарь ответов (по ключу = sha256 ОТ image_path / prompt):
        fake = FakeLLMProvider(responses={"abc123...": {"visible_application": "VS Code", ...}})

        # 2. Через директорию (загружает все *.json как dict[hash → payload]):
        fake = FakeLLMProvider.from_directory(Path("fixtures/llm_responses"))

        # 3. Программно — устанавливать default ответы по типу схемы:
        fake.set_default(VisionResult, {"screenshot_id": "...", ...})
    """

    def __init__(self, responses: Mapping[str, dict[str, object]] | None = None) -> None:
        self._responses: dict[str, dict[str, object]] = dict(responses or {})
        self._defaults_by_schema: dict[str, dict[str, object]] = {}
        self.calls: list[dict[str, object]] = []  # лог вызовов для assert'ов в тестах

    @classmethod
    def from_directory(cls, directory: Path) -> FakeLLMProvider:
        """Загрузить все *.json из директории.

        Имя файла без расширения = ключ.
        """
        responses: dict[str, dict[str, object]] = {}
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError(f"{path} must contain a JSON object")
                responses[path.stem] = data
        return cls(responses=responses)

    def set_default(self, schema: type[BaseModel], payload: dict[str, object]) -> None:
        """Дефолтный ответ для всех вызовов с этой схемой если ключ не найден."""
        self._defaults_by_schema[schema.__name__] = payload

    def set_response(self, key: str, payload: dict[str, object]) -> None:
        self._responses[key] = payload

    @staticmethod
    def hash_key(*parts: str | bytes | Path) -> str:
        h = hashlib.sha256()
        for p in parts:
            if isinstance(p, Path):
                h.update(str(p.resolve()).encode())
            elif isinstance(p, bytes):
                h.update(p)
            else:
                h.update(p.encode())
        return h.hexdigest()[:32]

    async def vision_analyze(
        self,
        image: Path | bytes,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "vision_primary",
        temperature: float = 0.0,
    ) -> T:
        # Ключ = stem имени файла (если Path) или хеш от image+prompt.
        # Отбрасываем ".redacted" суффикс — после image_redaction файл будет foo.redacted.png,
        # а в фикстурах ключ — "foo".
        if isinstance(image, Path):
            key = image.stem
            if key.endswith(".redacted"):
                key = key[: -len(".redacted")]
        else:
            key = self.hash_key(image, prompt)
        self.calls.append(
            {
                "method": "vision_analyze",
                "key": key,
                "model_alias": model_alias,
                "schema": response_schema.__name__,
            }
        )
        return self._build_response(key, response_schema)

    async def classify(
        self,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "text_primary",
        temperature: float = 0.0,
    ) -> T:
        key = self.hash_key(prompt)
        self.calls.append(
            {
                "method": "classify",
                "key": key,
                "model_alias": model_alias,
                "schema": response_schema.__name__,
            }
        )
        return self._build_response(key, response_schema)

    async def embed(
        self,
        text: str,
        *,
        model_alias: str = "embed_primary",
    ) -> list[float]:
        # Детерминистичный фейковый embedding: байты sha256 → 32 float'а в [-1, 1]
        h = hashlib.sha256(text.encode()).digest()
        return [(b - 128) / 128.0 for b in h]

    def _build_response(self, key: str, schema: type[T]) -> T:
        payload = self._responses.get(key) or self._defaults_by_schema.get(schema.__name__)
        if payload is None:
            raise LLMResponseValidationError(
                schema.__name__,
                f"no fake response registered for key={key!r} or schema={schema.__name__!r}",
            )
        try:
            return schema.model_validate(payload)
        except ValidationError as e:
            raise LLMResponseValidationError(
                schema.__name__,
                f"fake response invalid: {e.errors()}",
            ) from e
