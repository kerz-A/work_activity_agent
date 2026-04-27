"""FakeLLMProvider — детерминистичная замена LLM для тестов и dry-run.

Возвращает заранее записанные JSON-ответы по ключу. Не делает реальных API-вызовов.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from work_activity_agent.domain.enums import ActivityType
from work_activity_agent.domain.errors import LLMResponseValidationError

T = TypeVar("T", bound=BaseModel)

# В classify-промпт всегда вшит vision_json с полем screenshot_id —
# вытаскиваем его, чтобы тесты могли мапить per-screenshot ответы.
_SCREENSHOT_ID_RE = re.compile(r'"screenshot_id"\s*:\s*"([^"]+)"')


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
        # Per-screenshot маппинг для classify: screenshot_id → activity_type/overrides.
        self._classifications_by_id: dict[str, dict[str, Any]] = {}
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

    def set_classification_for(
        self,
        screenshot_id: str,
        activity_type: ActivityType,
        *,
        category: str = "test",
        evidence: tuple[str, ...] = ("fake_evidence",),
        confidence: float = 0.9,
    ) -> None:
        """Зарегистрировать ClassificationResult для конкретного screenshot_id.

        Используется в integration-тестах: достаточно объявить какие скрины
        должны получить IDLE_STATIC / JOB_SEARCH_SIGNAL и т.п., без склеивания
        промптов вручную.
        """
        self._classifications_by_id[screenshot_id] = {
            "screenshot_id": screenshot_id,
            "activity_type": activity_type.value,
            "category": category,
            "evidence": list(evidence),
            "confidence": confidence,
        }

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
            # Подменяем screenshot_id в дефолтном payload реальным stem'ом — иначе
            # set_default(VisionResult, {...}) даст всем скринам одинаковый id "default",
            # и classify-промпт потом не сможет матчить per-screenshot ответы.
            overrides: dict[str, Any] | None = {"screenshot_id": key}
        else:
            key = self.hash_key(image, prompt)
            overrides = None
        self.calls.append(
            {
                "method": "vision_analyze",
                "key": key,
                "model_alias": model_alias,
                "schema": response_schema.__name__,
            }
        )
        return self._build_response(key, response_schema, overrides=overrides)

    async def classify(
        self,
        prompt: str,
        response_schema: type[T],
        *,
        model_alias: str = "text_primary",
        temperature: float = 0.0,
    ) -> T:
        screenshot_id = self._extract_screenshot_id(prompt)
        key = self.hash_key(prompt)
        self.calls.append(
            {
                "method": "classify",
                "key": key,
                "screenshot_id": screenshot_id or "",
                "model_alias": model_alias,
                "schema": response_schema.__name__,
            }
        )
        if (
            screenshot_id is not None
            and screenshot_id in self._classifications_by_id
            and response_schema.__name__ == "ClassificationResult"
        ):
            payload = self._classifications_by_id[screenshot_id]
            return response_schema.model_validate(payload)
        # Если schema имеет поле screenshot_id, подставим реальный из промпта,
        # иначе все default-ответы будут с одинаковым "default" id.
        overrides: dict[str, Any] | None = None
        if screenshot_id is not None and "screenshot_id" in response_schema.model_fields:
            overrides = {"screenshot_id": screenshot_id}
        return self._build_response(key, response_schema, overrides=overrides)

    @staticmethod
    def _extract_screenshot_id(prompt: str) -> str | None:
        # Берём ПОСЛЕДНЕЕ вхождение: few-shot примеры в промпте содержат свои
        # "screenshot_id": "ex1"..."ex5" в начале, а реальный target — в конце,
        # внутри vision_json для текущего скриншота.
        matches = _SCREENSHOT_ID_RE.findall(prompt)
        return matches[-1] if matches else None

    async def embed(
        self,
        text: str,
        *,
        model_alias: str = "embed_primary",
    ) -> list[float]:
        # Детерминистичный фейковый embedding: байты sha256 → 32 float'а в [-1, 1]
        h = hashlib.sha256(text.encode()).digest()
        return [(b - 128) / 128.0 for b in h]

    def _build_response(
        self,
        key: str,
        schema: type[T],
        *,
        overrides: dict[str, Any] | None = None,
    ) -> T:
        payload = self._responses.get(key) or self._defaults_by_schema.get(schema.__name__)
        if payload is None:
            raise LLMResponseValidationError(
                schema.__name__,
                f"no fake response registered for key={key!r} or schema={schema.__name__!r}",
            )
        merged: dict[str, Any] = {**payload, **(overrides or {})}
        try:
            return schema.model_validate(merged)
        except ValidationError as e:
            raise LLMResponseValidationError(
                schema.__name__,
                f"fake response invalid: {e.errors()}",
            ) from e
