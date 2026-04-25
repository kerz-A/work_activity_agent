"""Integration тест: граф со смесью продуктивности и risk-сигналов."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from PIL import Image

from work_activity_agent.application.graph import build_graph
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
    RiskFlagType,
)
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.infrastructure.llm.fake_provider import FakeLLMProvider


@pytest.fixture
def risky_input(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    base = datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
    entries = []
    # 3 productive + 2 job_search
    for i in range(3):
        img = Image.new("RGB", (100, 100), color=(50, 50, 50))
        path = input_dir / f"prod_{i}.png"
        img.save(path)
        entries.append(
            {
                "file": f"prod_{i}.png",
                "employee_id": "dev_x",
                "project_id": "proj_x",
                "task_id": "TASK-1",
                "tracked_task_title": "Build feature",
                "captured_at": base.replace(hour=9 + i).isoformat(),
                "tracked_minutes": 60,
            }
        )
    for i in range(2):
        img = Image.new("RGB", (100, 100), color=(0, 102, 196))
        path = input_dir / f"job_{i}.png"
        img.save(path)
        entries.append(
            {
                "file": f"job_{i}.png",
                "employee_id": "dev_x",
                "project_id": "proj_x",
                "task_id": "TASK-1",
                "tracked_task_title": "Build feature",
                "captured_at": base.replace(hour=14 + i).isoformat(),
                "tracked_minutes": 60,
            }
        )

    (input_dir / "manifest.yaml").write_text(
        yaml.safe_dump({"version": 1, "screenshots": entries}, allow_unicode=True),
        encoding="utf-8",
    )
    return input_dir


def _setup_fake_responses(fake: FakeLLMProvider) -> None:
    # Настраиваем responses по stem'ам файлов
    for i in range(3):
        fake.set_response(
            f"prod_{i}",
            {
                "screenshot_id": f"prod_{i}",
                "visible_application": "VS Code",
                "visible_site": None,
                "visible_page_type": "Code editor",
                "visible_text": ["function build()"],
                "interpreted_activity": "Coding feature",
                "extracted_metadata": {},
                "confidence": 0.9,
                "model_used": "fake/test",
            },
        )
    for i in range(2):
        fake.set_response(
            f"job_{i}",
            {
                "screenshot_id": f"job_{i}",
                "visible_application": "Chrome",
                "visible_site": "hh.ru",
                "visible_page_type": "Vacancy",
                "visible_text": ["Senior Python Developer", "Salary"],
                "interpreted_activity": "Browsing job vacancies",
                "extracted_metadata": {},
                "confidence": 0.95,
                "model_used": "fake/test",
            },
        )

    # Дефолтные ответы для классификатора и relevance — основываем на свойствах
    # FakeLLM хеширует по prompt — так что разные скрины дадут разные хеши.
    # Используем set_default чтобы упростить.
    fake.set_default(
        ClassificationResult,
        {
            "screenshot_id": "default",
            "activity_type": ActivityType.PRODUCTIVE_WORK.value,
            "category": "x",
            "evidence": ["e"],
            "confidence": 0.9,
        },
    )
    fake.set_default(
        RelevanceResult,
        {
            "screenshot_id": "default",
            "tracked_task": "Build feature",
            "screenshot_activity": "x",
            "relevance": RelevanceLevel.LOW.value,
            "risk_flags": [RiskFlagType.JOB_SEARCH_SITE.value],
            "confidence": 0.85,
            "note": "Job search website detected",
        },
    )


@pytest.mark.integration
async def test_with_risks(risky_input: Path, test_deps: Deps) -> None:
    _setup_fake_responses(test_deps.llm)  # type: ignore[arg-type]

    graph = build_graph(test_deps)
    final_state_raw = await graph.ainvoke(AgentState(input_dir=risky_input))
    final_state = AgentState.model_validate(final_state_raw)

    assert len(final_state.screenshots) == 5
    assert len(final_state.employee_reports) == 1

    report = final_state.employee_reports[0]
    # Должны быть risk_flags из relevance.risk_flags (job_search_site по дефолту на всех)
    assert len(report.risk_flags) > 0
    flag_types = {f.type for f in report.risk_flags}
    assert RiskFlagType.JOB_SEARCH_SITE in flag_types

    # Все флаги requires_human_review
    assert all(f.requires_human_review for f in report.risk_flags)

    # screenshot_table должен содержать запись с review=True
    review_rows = [row for row in final_state.screenshot_table if row.review]
    assert len(review_rows) > 0
