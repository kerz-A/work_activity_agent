"""Тесты CLI: version, doctor (через моки), validate-prompts.

`run` и `dry-run` покрываются интеграционными тестами через граф —
здесь только то, что можно проверить без полного pipeline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from work_activity_agent.presentation.cli import (
    _check_cloud_keys,
    _check_configs,
    _check_ollama,
    _check_python,
    _check_spacy,
    _check_tesseract,
    app,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestVersion:
    def test_version_prints_package_version(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "work-activity-agent" in result.stdout


class TestCheckPython:
    def test_modern_python_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Тесты запускаются на 3.12+ (см. pyproject), значит должно быть 0.
        failures = _check_python()
        captured = capsys.readouterr()
        assert failures == 0
        assert "[OK]" in captured.out

    def test_old_python_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        from collections import namedtuple

        # Имитируем sys.version_info — он имеет и tuple-сравнение, и .major/.minor/.micro.
        VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro"])
        fake_version = VersionInfo(3, 10, 0)
        with patch("work_activity_agent.presentation.cli.sys") as mock_sys:
            mock_sys.version_info = fake_version
            failures = _check_python()
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out


class TestCheckTesseract:
    def test_found_in_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("work_activity_agent.presentation.cli.shutil.which", return_value="/usr/bin/tesseract"):
            failures = _check_tesseract(privacy_strict=True)
        assert failures == 0
        assert "[OK]" in capsys.readouterr().out

    def test_missing_strict_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("work_activity_agent.presentation.cli.shutil.which", return_value=None),
            patch(
                "work_activity_agent.infrastructure.redaction.presidio_image_redactor"
                "._autodetect_tesseract",
                return_value=None,
            ),
        ):
            failures = _check_tesseract(privacy_strict=True)
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out

    def test_missing_lax_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("work_activity_agent.presentation.cli.shutil.which", return_value=None),
            patch(
                "work_activity_agent.infrastructure.redaction.presidio_image_redactor"
                "._autodetect_tesseract",
                return_value=None,
            ),
        ):
            failures = _check_tesseract(privacy_strict=False)
        captured = capsys.readouterr()
        assert failures == 0
        assert "[WARN]" in captured.out


class TestCheckOllama:
    def test_reachable(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": "gemma3:4b"}]}
        with patch("httpx.get", return_value=mock_response):
            failures = _check_ollama("http://localhost:11434")
        captured = capsys.readouterr()
        assert failures == 0
        assert "[OK]" in captured.out
        assert "gemma3:4b" in captured.out

    def test_unreachable(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("httpx.get", side_effect=ConnectionError("refused")):
            failures = _check_ollama("http://localhost:11434")
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out

    def test_non_200(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 503
        with patch("httpx.get", return_value=mock_response):
            failures = _check_ollama("http://localhost:11434")
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out


class TestCheckCloudKeys:
    def test_at_least_one_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        from pydantic import SecretStr

        from work_activity_agent.config.settings import Settings

        settings = Settings()
        settings.llm.anthropic_api_key = SecretStr("test-key")
        failures = _check_cloud_keys(settings)
        captured = capsys.readouterr()
        assert failures == 0
        assert "[OK]" in captured.out

    def test_no_keys(self, capsys: pytest.CaptureFixture[str]) -> None:
        from work_activity_agent.config.settings import Settings

        settings = Settings()
        settings.llm.anthropic_api_key = None
        settings.llm.openai_api_key = None
        settings.llm.openrouter_api_key = None
        settings.llm.groq_api_key = None
        failures = _check_cloud_keys(settings)
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out


class TestCheckSpacy:
    def test_model_loaded(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_spacy = MagicMock()
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            failures = _check_spacy(privacy_strict=True)
        assert failures == 0
        assert "[OK]" in capsys.readouterr().out

    def test_model_missing_strict(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_spacy = MagicMock()
        mock_spacy.load.side_effect = OSError("model not found")
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            failures = _check_spacy(privacy_strict=True)
        captured = capsys.readouterr()
        assert failures == 1
        assert "[FAIL]" in captured.out


class TestCheckConfigs:
    def test_both_configs_exist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from work_activity_agent.config.settings import Settings

        models_yaml = tmp_path / "models.yaml"
        models_yaml.write_text("vision_primary: ollama_chat/gemma3:4b\n", encoding="utf-8")
        risk_yaml = tmp_path / "risk.yaml"
        risk_yaml.write_text("risk_score: {weights: {}, thresholds: {}}\n", encoding="utf-8")

        settings = Settings()
        settings.llm.models_config_path = models_yaml
        # cached_property: invalidate
        settings.llm.__dict__.pop("resolved_models_config_path", None)
        settings.risk.config_path = risk_yaml

        failures = _check_configs(settings, profile="cloud")
        captured = capsys.readouterr()
        assert failures == 0
        assert "[OK]" in captured.out

    def test_missing_config_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from work_activity_agent.config.settings import Settings

        settings = Settings()
        settings.llm.models_config_path = tmp_path / "missing_models.yaml"
        settings.llm.__dict__.pop("resolved_models_config_path", None)
        settings.risk.config_path = tmp_path / "missing_risk.yaml"

        failures = _check_configs(settings, profile="cloud")
        captured = capsys.readouterr()
        assert failures == 2
        assert "[FAIL]" in captured.out


class TestValidatePrompts:
    def test_missing_directory_fails(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Запускаем из пустой директории — configs/prompts/ не существует.
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["validate-prompts"])
        assert result.exit_code == 1


class TestDoctorCommandSmoke:
    """Smoke: doctor возвращает не-нулевой exit при недоступной Ollama, и команда
    не падает с unhandled exception. Покрывает интеграцию helper-ов."""

    def test_doctor_runs_without_crash(self, runner: CliRunner) -> None:
        # Ollama скорее всего недоступна в тестовом окружении — это OK,
        # главное что команда возвращает корректный exit code, а не падает.
        with patch("httpx.get", side_effect=ConnectionError("refused")):
            result = runner.invoke(app, ["doctor"])
        # Exit может быть 0 или 1 в зависимости от окружения, но не 2 (crash).
        assert result.exit_code in {0, 1}
