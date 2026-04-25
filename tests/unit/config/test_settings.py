"""Тесты Settings, LLMSettings, RiskSettings, ObservabilitySettings."""

from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from work_activity_agent.config.settings import (
    LLMSettings,
    ObservabilitySettings,
    RiskSettings,
    Settings,
)


class TestLLMSettings:
    def test_defaults(self) -> None:
        s = LLMSettings()
        assert s.max_concurrent_vision == 4
        assert s.request_timeout_s == 60
        assert s.soft_budget_usd == 5.0
        assert s.anthropic_api_key is None

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("LLM_MAX_CONCURRENT_VISION", "8")
        s = LLMSettings()
        assert isinstance(s.anthropic_api_key, SecretStr)
        assert s.anthropic_api_key.get_secret_value() == "sk-ant-test"
        assert s.max_concurrent_vision == 8

    def test_max_concurrent_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MAX_CONCURRENT_VISION", "0")
        with pytest.raises(ValidationError):
            LLMSettings()

    def test_model_aliases_loads_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "models.yaml"
        path.write_text(
            "vision_primary: anthropic/claude-sonnet-4-5\ntext_primary: gpt-4o-mini\n",
            encoding="utf-8",
        )
        s = LLMSettings(models_config_path=path)
        aliases = s.model_aliases
        assert aliases["vision_primary"] == "anthropic/claude-sonnet-4-5"
        assert aliases["text_primary"] == "gpt-4o-mini"

    def test_model_aliases_missing_file_returns_empty(self, tmp_path: Path) -> None:
        s = LLMSettings(models_config_path=tmp_path / "missing.yaml")
        assert s.model_aliases == {}


class TestRiskSettings:
    def _build_config(self, tmp_path: Path) -> Path:
        path = tmp_path / "default.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "risk_score": {
                        "weights": {"static_ratio": 0.25, "task_mismatch": 0.20},
                        "thresholds": {"low": 30, "medium": 60},
                    },
                    "work_activity_score": {
                        "weights": {"task_alignment": 0.25, "screen_dynamics": 0.15},
                        "thresholds": {"low": 40, "medium": 70},
                    },
                    "timeline": {"static_screen": {"min_consecutive": 4}},
                    "vision": {"max_concurrent": 4},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_loads_risk_weights(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=self._build_config(tmp_path))
        assert s.risk_weights == {"static_ratio": 0.25, "task_mismatch": 0.20}

    def test_loads_risk_thresholds(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=self._build_config(tmp_path))
        assert s.risk_thresholds == {"low": 30, "medium": 60}

    def test_loads_work_activity_weights(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=self._build_config(tmp_path))
        assert s.work_activity_weights == {
            "task_alignment": 0.25,
            "screen_dynamics": 0.15,
        }

    def test_loads_work_activity_thresholds(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=self._build_config(tmp_path))
        assert s.work_activity_thresholds == {"low": 40, "medium": 70}

    def test_loads_timeline_config(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=self._build_config(tmp_path))
        assert s.timeline_config == {"static_screen": {"min_consecutive": 4}}

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        s = RiskSettings(config_path=tmp_path / "missing.yaml")
        with pytest.raises(FileNotFoundError):
            _ = s.risk_weights


class TestObservabilitySettings:
    def test_defaults(self) -> None:
        s = ObservabilitySettings()
        assert s.log_level == "INFO"
        assert s.json_logs is True
        assert s.enable_tracing is False

    def test_invalid_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OBSERVABILITY_LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError):
            ObservabilitySettings()


class TestSettings:
    def test_default_paths(self) -> None:
        s = Settings()
        assert s.input_dir == Path("./data/screenshots")
        assert s.output_dir == Path("./data/reports")
        assert s.checkpoint_dir == Path("./.checkpoints")

    def test_subcomponents_built(self) -> None:
        s = Settings()
        assert isinstance(s.llm, LLMSettings)
        assert isinstance(s.risk, RiskSettings)
        assert isinstance(s.observability, ObservabilitySettings)
