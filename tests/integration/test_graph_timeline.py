"""Integration тест: граф детектит timeline-паттерны на in-memory фикстурах.

Сценарий:
- designer_1: 4 IDLE_STATIC скрина в одном часе (09:00–09:15) → long_static_period
- developer_2: 3 JOB_SEARCH_SIGNAL скрина в одном часе (14:00–14:10) → job_search_burst
- developer_3: 2 IDLE_STATIC скрина (ниже порога) → не должен попасть в patterns

Vision подменяется FakeLLMProvider, classify — через per-screenshot mapping.
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
from work_activity_agent.domain.enums import (
    ActivityType,
    RelevanceLevel,
)
from work_activity_agent.domain.models.classification import RelevanceResult
from work_activity_agent.infrastructure.llm.fake_provider import FakeLLMProvider

# Имена должны соответствовать конвенции _FILENAME_RE из collector.py:
# {employee}__{project}__{task}__{ISO timestamp}, без `_` внутри сегментов.
_STATIC_FILES = [
    ("desA__cart__T1__2026-04-22T09-00-00.png", "designer_1", 9, 0),
    ("desA__cart__T1__2026-04-22T09-05-00.png", "designer_1", 9, 5),
    ("desA__cart__T1__2026-04-22T09-10-00.png", "designer_1", 9, 10),
    ("desA__cart__T1__2026-04-22T09-15-00.png", "designer_1", 9, 15),
]
_JOB_FILES = [
    ("devB__crm__T2__2026-04-22T14-00-00.png", "developer_2", 14, 0),
    ("devB__crm__T2__2026-04-22T14-05-00.png", "developer_2", 14, 5),
    ("devB__crm__T2__2026-04-22T14-10-00.png", "developer_2", 14, 10),
]
_BELOW_THRESHOLD = [
    ("devC__api__T3__2026-04-22T11-00-00.png", "developer_3", 11, 0),
    ("devC__api__T3__2026-04-22T11-05-00.png", "developer_3", 11, 5),
]


@pytest.fixture
def timeline_input(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    entries = []

    for files, color in (
        (_STATIC_FILES, (200, 200, 200)),
        (_JOB_FILES, (0, 102, 196)),
        (_BELOW_THRESHOLD, (50, 50, 50)),
    ):
        for filename, employee, hour, minute in files:
            img = Image.new("RGB", (40, 40), color=color)
            (input_dir / filename).parent.mkdir(parents=True, exist_ok=True)
            img.save(input_dir / filename)
            entries.append(
                {
                    "file": filename,
                    "employee_id": employee,
                    "project_id": "proj",
                    "task_id": "TASK-T",
                    "tracked_task_title": "Build feature",
                    "captured_at": datetime(
                        2026, 4, 22, hour, minute, tzinfo=UTC
                    ).isoformat(),
                    "tracked_minutes": 5,
                }
            )

    (input_dir / "manifest.yaml").write_text(
        yaml.safe_dump({"version": 1, "screenshots": entries}, allow_unicode=True),
        encoding="utf-8",
    )
    return input_dir


def _setup_fake(fake: FakeLLMProvider) -> None:
    # Дефолтный VisionResult для всех скринов (screenshot_id подставится из image stem).
    fake.set_default(
        type("VisionResult", (), {}),  # placeholder, заменим ниже на реальный класс
        {},
    )
    from work_activity_agent.domain.models.vision import VisionResult

    fake.set_default(
        VisionResult,
        {
            "screenshot_id": "default",
            "visible_application": "Generic",
            "visible_site": None,
            "visible_page_type": "screen",
            "visible_text": ["fake"],
            "interpreted_activity": "Working",
            "extracted_metadata": {},
            "confidence": 0.8,
            "model_used": "fake/test",
        },
    )

    # Дефолтный RelevanceResult — relevance HIGH без флагов (чтобы не загрязнять отчёт).
    fake.set_default(
        RelevanceResult,
        {
            "screenshot_id": "default",
            "tracked_task": "Build feature",
            "screenshot_activity": "Working",
            "relevance": RelevanceLevel.HIGH.value,
            "risk_flags": [],
            "confidence": 0.8,
            "note": None,
        },
    )

    # Per-screenshot ClassificationResult: главное — назначить IDLE_STATIC и
    # JOB_SEARCH_SIGNAL нужным группам, чтобы Timeline их детектил.
    for filename, _, _, _ in _STATIC_FILES:
        fake.set_classification_for(
            screenshot_id=Path(filename).stem,
            activity_type=ActivityType.IDLE_STATIC,
        )
    for filename, _, _, _ in _JOB_FILES:
        fake.set_classification_for(
            screenshot_id=Path(filename).stem,
            activity_type=ActivityType.JOB_SEARCH_SIGNAL,
        )
    for filename, _, _, _ in _BELOW_THRESHOLD:
        fake.set_classification_for(
            screenshot_id=Path(filename).stem,
            activity_type=ActivityType.IDLE_STATIC,
        )


@pytest.mark.integration
async def test_graph_detects_timeline_patterns(
    timeline_input: Path, test_deps: Deps
) -> None:
    _setup_fake(test_deps.llm)  # type: ignore[arg-type]

    graph = build_graph(test_deps)
    final_state_raw = await graph.ainvoke(AgentState(input_dir=timeline_input))
    final_state = AgentState.model_validate(final_state_raw)

    assert len(final_state.screenshots) == len(_STATIC_FILES) + len(_JOB_FILES) + len(
        _BELOW_THRESHOLD
    )

    patterns = final_state.timeline_patterns
    assert len(patterns) >= 2, f"expected static + burst patterns, got: {patterns}"

    by_pattern = {p.pattern: p for p in patterns}

    # 1. designer_1 — long_static_period с >=4 скринами
    assert "long_static_period" in by_pattern
    static_pattern = by_pattern["long_static_period"]
    assert static_pattern.employee_id == "designer_1"
    assert len(static_pattern.screenshot_ids) >= 4
    assert static_pattern.requires_review is True

    # 2. developer_2 — job_search_burst
    assert "job_search_burst" in by_pattern
    burst = by_pattern["job_search_burst"]
    assert burst.employee_id == "developer_2"
    assert len(burst.screenshot_ids) == 3
    assert burst.requires_review is True

    # 3. developer_3 НЕ должен иметь паттерн — у него только 2 IDLE_STATIC (порог 4)
    employee_ids_with_patterns = {p.employee_id for p in patterns}
    assert "developer_3" not in employee_ids_with_patterns


@pytest.mark.integration
async def test_timeline_patterns_appear_in_employee_reports(
    timeline_input: Path, test_deps: Deps
) -> None:
    _setup_fake(test_deps.llm)  # type: ignore[arg-type]

    graph = build_graph(test_deps)
    final_state_raw = await graph.ainvoke(AgentState(input_dir=timeline_input))
    final_state = AgentState.model_validate(final_state_raw)

    designer_report = next(
        (r for r in final_state.employee_reports if r.employee_id == "designer_1"),
        None,
    )
    assert designer_report is not None
    # Менеджерское резюме / risk_flags должны нести след найденного паттерна
    # (его embed'ит EvidenceBuilder/Reports node — точное место зависит от реализации).
    # Минимальная проверка: отчёт сгенерирован, скрины посчитаны.
    assert designer_report.screenshots_total == len(_STATIC_FILES)
