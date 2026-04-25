"""Глобальные pytest фикстуры."""

from __future__ import annotations

from pathlib import Path

import pytest

from work_activity_agent.config.container import Deps, build_dependencies
from work_activity_agent.config.settings import (
    LLMSettings,
    ObservabilitySettings,
    RiskSettings,
    Settings,
)
from work_activity_agent.infrastructure.llm.fake_provider import FakeLLMProvider

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    """Чистый FakeLLMProvider, заполняется в каждом тесте через set_default/set_response."""
    return FakeLLMProvider()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Settings с tmp_path для output, реальный configs/ для конфигов."""
    return Settings(
        llm=LLMSettings(models_config_path=PROJECT_ROOT / "configs" / "models.yaml"),
        risk=RiskSettings(config_path=PROJECT_ROOT / "configs" / "default.yaml"),
        observability=ObservabilitySettings(log_level="WARNING", json_logs=False),
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        checkpoint_dir=tmp_path / "checkpoints",
    )


@pytest.fixture
def test_deps(test_settings: Settings) -> Deps:
    """Deps с FakeLLM + Noop redactor для CI."""
    return build_dependencies(
        test_settings,
        use_fake_llm=True,
        use_noop_redactor=True,
    )
