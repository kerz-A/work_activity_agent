"""Тесты приоритетов captured_at в Collector.

Источники captured_at в порядке приоритета:
1. manifest.captured_at (авторитетный для прода)
2. Timestamp из имени файла по конвенции _FILENAME_RE
3. mtime файла на диске (fallback)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from PIL import Image

from work_activity_agent.application.nodes.collector import make_collector_node
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps


def _save_dummy_png(path: Path) -> None:
    Image.new("RGB", (10, 10)).save(path)


@pytest.fixture
def input_dir(tmp_path: Path) -> Path:
    d = tmp_path / "input"
    d.mkdir()
    return d


def test_manifest_captured_at_takes_priority(test_deps: Deps, input_dir: Path) -> None:
    """captured_at из manifest должен использоваться, даже если у файла свежий mtime."""
    file_path = input_dir / "screenshot_001.png"
    _save_dummy_png(file_path)

    expected_at = datetime(2026, 4, 22, 9, 0, 0, tzinfo=UTC)
    manifest = {
        "version": 1,
        "screenshots": [
            {
                "file": "screenshot_001.png",
                "employee_id": "dev_1",
                "captured_at": expected_at.isoformat(),
            }
        ],
    }
    (input_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    node = make_collector_node(test_deps)
    state = node(AgentState(input_dir=input_dir))

    assert len(state.screenshots) == 1
    assert state.screenshots[0].captured_at == expected_at


def test_falls_back_to_mtime_without_captured_at_in_manifest(
    test_deps: Deps, input_dir: Path
) -> None:
    """Без captured_at в manifest используется mtime файла."""
    file_path = input_dir / "screenshot_002.png"
    _save_dummy_png(file_path)
    mtime_before = file_path.stat().st_mtime

    manifest = {
        "version": 1,
        "screenshots": [
            {"file": "screenshot_002.png", "employee_id": "dev_1"},
        ],
    }
    (input_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    node = make_collector_node(test_deps)
    state = node(AgentState(input_dir=input_dir))

    assert len(state.screenshots) == 1
    # mtime может быть округлен до секунд — допускаем небольшую погрешность
    assert abs(state.screenshots[0].captured_at.timestamp() - mtime_before) < 2.0


def test_filename_convention_takes_priority_over_mtime(
    test_deps: Deps, input_dir: Path
) -> None:
    """Имя файла по конвенции {emp}__{proj}__{task}__{ts} обходит mtime."""
    name = "dev1__proj__T1__2026-03-15T08-30-00.png"
    file_path = input_dir / name
    _save_dummy_png(file_path)
    # Свежий mtime — но он не должен победить timestamp из имени
    time.sleep(0.01)

    node = make_collector_node(test_deps)
    state = node(AgentState(input_dir=input_dir))

    assert len(state.screenshots) == 1
    expected = datetime(2026, 3, 15, 8, 30, 0, tzinfo=UTC)
    assert state.screenshots[0].captured_at == expected


def test_manifest_captured_at_overrides_filename_convention(
    test_deps: Deps, input_dir: Path
) -> None:
    """Даже если файл подходит под конвенцию имени — manifest имеет приоритет."""
    name = "dev1__proj__T1__2099-12-31T23-59-59.png"
    file_path = input_dir / name
    _save_dummy_png(file_path)

    expected_at = datetime(2026, 4, 22, 9, 0, 0, tzinfo=UTC)
    manifest = {
        "version": 1,
        "screenshots": [
            {
                "file": name,
                "employee_id": "dev_1",
                "captured_at": expected_at.isoformat(),
            }
        ],
    }
    (input_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    node = make_collector_node(test_deps)
    state = node(AgentState(input_dir=input_dir))

    assert state.screenshots[0].captured_at == expected_at
