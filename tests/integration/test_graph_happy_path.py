"""Integration тест: граф целиком на 5 productive скринах.

Цель: проверить что pipeline работает end-to-end на FakeLLM:
- все узлы запускаются
- финальные отчёты собираются
- risk_score = LOW, work_activity_score = HIGH
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from PIL import Image

from work_activity_agent.application.graph import build_graph
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import ActivityType, RelevanceLevel
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.vision import VisionResult


@pytest.fixture
def happy_input_dir(tmp_path: Path) -> Path:
    """Создаёт 5 placeholder PNG + manifest.yaml."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    base = datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
    entries = []
    for i in range(5):
        # Простейший PNG через Pillow
        img = Image.new("RGB", (100, 100), color=(45, 55, 72))
        path = input_dir / f"happy_{i}.png"
        img.save(path)
        entries.append(
            {
                "file": f"happy_{i}.png",
                "employee_id": "developer_1",
                "project_id": "client_crm",
                "task_id": "TASK-100",
                "tracked_task_title": "Implement feature X",
                "captured_at": (base.replace(hour=9 + i)).isoformat(),
                "tracked_minutes": 60,
                "app_hint": "VS Code",
            }
        )

    manifest = {"version": 1, "screenshots": entries}
    (input_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    return input_dir


@pytest.fixture
def happy_deps_with_responses(test_deps: Deps, happy_input_dir: Path) -> Deps:
    """Регистрируем дефолтные FakeLLM ответы для VisionResult, ClassificationResult, RelevanceResult."""
    fake_llm = test_deps.llm  # FakeLLMProvider

    # Дефолтный VisionResult — будет применяться когда ключ не найден
    fake_llm.set_default(  # type: ignore[attr-defined]
        VisionResult,
        {
            "screenshot_id": "default",
            "visible_application": "VS Code",
            "visible_site": None,
            "visible_page_type": "Code editor",
            "visible_text": ["function shouldRetry()", "return isTransient(error)"],
            "interpreted_activity": "Editing TypeScript code in payment service",
            "extracted_metadata": {},
            "confidence": 0.85,
            "model_used": "fake/test",
        },
    )

    fake_llm.set_default(  # type: ignore[attr-defined]
        ClassificationResult,
        {
            "screenshot_id": "default",
            "activity_type": ActivityType.PRODUCTIVE_WORK.value,
            "category": "software_development",
            "evidence": ["VS Code открыт", "виден production код"],
            "confidence": 0.9,
        },
    )

    fake_llm.set_default(  # type: ignore[attr-defined]
        RelevanceResult,
        {
            "screenshot_id": "default",
            "tracked_task": "Implement feature X",
            "screenshot_activity": "Editing TypeScript code",
            "relevance": RelevanceLevel.HIGH.value,
            "risk_flags": [],
            "confidence": 0.9,
            "note": None,
        },
    )

    return test_deps


@pytest.mark.integration
async def test_happy_path_end_to_end(
    happy_input_dir: Path,
    happy_deps_with_responses: Deps,
) -> None:
    # Проверяем что configs/prompts/ существует — необходимо для рендеринга промптов.
    project_root = Path(__file__).resolve().parents[2]  # noqa: ASYNC240 — async контекст вне горячего пути
    prompts_dir = project_root / "configs" / "prompts"
    assert prompts_dir.exists(), "configs/prompts должен существовать для теста"

    graph = build_graph(happy_deps_with_responses)

    initial_state = AgentState(input_dir=happy_input_dir)
    final_state_raw = await graph.ainvoke(initial_state)
    final_state = AgentState.model_validate(final_state_raw)

    # Базовые проверки
    assert len(final_state.screenshots) == 5
    assert len(final_state.redacted_screenshots) == 5
    assert len(final_state.vision_results) == 5
    assert len(final_state.classifications) == 5
    assert len(final_state.relevances) == 5

    # Должен быть собран дневной отчёт
    assert len(final_state.employee_reports) == 1
    report = final_state.employee_reports[0]
    assert report.employee_id == "developer_1"
    assert report.screenshots_total == 5

    # Risk score должен быть LOW (всё productive)
    from work_activity_agent.domain.enums import RiskLevel, WorkActivityLevel

    assert report.risk_score.level == RiskLevel.LOW
    # Work activity должен быть HIGH или MEDIUM (productive + aligned с задачей)
    assert report.work_activity_score.level in {
        WorkActivityLevel.HIGH,
        WorkActivityLevel.MEDIUM,
    }

    # Не должно быть risk_flags при чистом продуктивном дне
    assert len(report.risk_flags) == 0

    # Project report
    assert len(final_state.project_reports) == 1
    pr = final_state.project_reports[0]
    assert pr.project_id == "client_crm"
    assert pr.productive_ratio > 0.5

    # Файлы отчётов на диске
    output_files = list(happy_deps_with_responses.settings.output_dir.glob("*"))
    assert any("employee_developer_1" in f.name for f in output_files)
    assert any("project_client_crm" in f.name for f in output_files)
    assert any("screenshots_table" in f.name for f in output_files)
