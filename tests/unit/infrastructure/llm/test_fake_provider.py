"""Тесты FakeLLMProvider."""

import json
from pathlib import Path

import pytest

from work_activity_agent.domain.errors import LLMResponseValidationError
from work_activity_agent.domain.models.vision import VisionResult
from work_activity_agent.infrastructure.llm.fake_provider import FakeLLMProvider


class TestVisionAnalyze:
    @pytest.fixture
    def vision_payload(self) -> dict[str, object]:
        return {
            "screenshot_id": "scr_1",
            "visible_application": "VS Code",
            "interpreted_activity": "editing code",
            "confidence": 0.85,
            "model_used": "fake/test",
        }

    async def test_returns_response_by_path_stem(
        self, tmp_path: Path, vision_payload: dict[str, object]
    ) -> None:
        img = tmp_path / "scr_1.png"
        img.write_bytes(b"")
        fake = FakeLLMProvider(responses={"scr_1": vision_payload})
        result = await fake.vision_analyze(img, "any prompt", VisionResult)
        assert result.visible_application == "VS Code"

    async def test_uses_default_when_key_missing(
        self, tmp_path: Path, vision_payload: dict[str, object]
    ) -> None:
        img = tmp_path / "scr_1.png"
        img.write_bytes(b"")
        fake = FakeLLMProvider()
        fake.set_default(VisionResult, vision_payload)
        result = await fake.vision_analyze(img, "any prompt", VisionResult)
        assert result.visible_application == "VS Code"

    async def test_records_calls(self, tmp_path: Path, vision_payload: dict[str, object]) -> None:
        img = tmp_path / "scr_1.png"
        img.write_bytes(b"")
        fake = FakeLLMProvider(responses={"scr_1": vision_payload})
        await fake.vision_analyze(img, "prompt 1", VisionResult)
        await fake.vision_analyze(img, "prompt 2", VisionResult)
        assert len(fake.calls) == 2
        assert fake.calls[0]["method"] == "vision_analyze"

    async def test_no_response_raises(self, tmp_path: Path) -> None:
        img = tmp_path / "scr_1.png"
        img.write_bytes(b"")
        fake = FakeLLMProvider()
        with pytest.raises(LLMResponseValidationError):
            await fake.vision_analyze(img, "any", VisionResult)


class TestFromDirectory:
    def test_loads_json_files(self, tmp_path: Path) -> None:
        (tmp_path / "scr_1.json").write_text(
            json.dumps(
                {
                    "screenshot_id": "scr_1",
                    "visible_application": "VS Code",
                    "interpreted_activity": "x",
                    "confidence": 0.5,
                    "model_used": "fake/test",
                }
            ),
            encoding="utf-8",
        )
        fake = FakeLLMProvider.from_directory(tmp_path)
        assert "scr_1" in fake._responses

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        fake = FakeLLMProvider.from_directory(tmp_path / "missing")
        assert fake._responses == {}


class TestEmbed:
    async def test_returns_deterministic_embedding(self) -> None:
        fake = FakeLLMProvider()
        e1 = await fake.embed("hello")
        e2 = await fake.embed("hello")
        e3 = await fake.embed("world")
        assert e1 == e2  # deterministic
        assert e1 != e3
        assert len(e1) == 32
        assert all(-1.0 <= v <= 1.0 for v in e1)
