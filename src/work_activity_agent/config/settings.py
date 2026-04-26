"""Настройки приложения через pydantic-settings.

Иерархия:
- Settings — корневая
  - llm: LLMSettings (env_prefix=LLM_)
  - risk: RiskSettings (env_prefix=RISK_)
  - observability: ObservabilitySettings (env_prefix=OBSERVABILITY_)

Секреты — только из .env, никогда в коде.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Настройки LLM-провайдеров (LiteLLM)."""

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    # Ollama (локально, по умолчанию). API key не нужен, можно сменить URL.
    ollama_base_url: str = "http://localhost:11434"
    # Облачные провайдеры (опц., если меняешь configs/models.yaml).
    openrouter_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    huggingface_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    max_concurrent_vision: Annotated[int, Field(ge=1, le=32)] = 4
    request_timeout_s: Annotated[int, Field(ge=10, le=600)] = 60
    soft_budget_usd: Annotated[float, Field(ge=0.0)] = 5.0
    models_config_path: Path = Path("configs/models.yaml")

    @cached_property
    def model_aliases(self) -> dict[str, str]:
        """Загрузить alias → real model маппинг из YAML."""
        if not self.models_config_path.exists():
            return {}
        with self.models_config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"models config must be a dict, got {type(data).__name__}")
        return {str(k): str(v) for k, v in data.items()}


class RiskSettings(BaseSettings):
    """Веса и thresholds для Risk Score и Work Activity Score."""

    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    config_path: Path = Path("configs/default.yaml")

    @cached_property
    def _raw_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"risk config not found: {self.config_path}")
        with self.config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"risk config must be a dict, got {type(data).__name__}")
        return data

    @cached_property
    def risk_weights(self) -> dict[str, float]:
        weights = self._raw_config.get("risk_score", {}).get("weights", {})
        return {str(k): float(v) for k, v in weights.items()}

    @cached_property
    def risk_thresholds(self) -> dict[str, int]:
        t = self._raw_config.get("risk_score", {}).get("thresholds", {})
        return {str(k): int(v) for k, v in t.items()}

    @cached_property
    def work_activity_weights(self) -> dict[str, float]:
        weights = self._raw_config.get("work_activity_score", {}).get("weights", {})
        return {str(k): float(v) for k, v in weights.items()}

    @cached_property
    def work_activity_thresholds(self) -> dict[str, int]:
        t = self._raw_config.get("work_activity_score", {}).get("thresholds", {})
        return {str(k): int(v) for k, v in t.items()}

    @cached_property
    def timeline_config(self) -> dict[str, Any]:
        result = self._raw_config.get("timeline", {})
        return dict(result) if isinstance(result, dict) else {}

    @cached_property
    def vision_config(self) -> dict[str, Any]:
        result = self._raw_config.get("vision", {})
        return dict(result) if isinstance(result, dict) else {}


class ObservabilitySettings(BaseSettings):
    """Логирование и трассировка."""

    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_", env_file=".env", extra="ignore")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_logs: bool = True
    enable_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "work-activity-agent"


class Settings(BaseSettings):
    """Корневые настройки. Подкомпоненты — через Field(default_factory=...)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    input_dir: Path = Path("./data/screenshots")
    output_dir: Path = Path("./data/reports")
    checkpoint_dir: Path = Path("./.checkpoints")

    @field_validator("input_dir", "output_dir", "checkpoint_dir")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        return value.expanduser()
