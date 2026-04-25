"""Smoke-тест: проверка что пакет импортируется. Заглушка для CI на этапе 0."""

from work_activity_agent import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_importable() -> None:
    from work_activity_agent.presentation.cli import app

    assert app is not None
