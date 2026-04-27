"""Юнит-тесты Timeline-узла (ТЗ §6).

Проверяем именно ноду (не grouper), на in-memory Screenshot+ClassificationResult.
LLM не дёргается — Timeline узел работает только с уже готовыми классификациями.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from work_activity_agent.application.nodes.timeline import make_timeline_node
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.enums import ActivityType, RiskLevel
from work_activity_agent.domain.models.classification import ClassificationResult
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata


def _ss(
    sid: str,
    hour: int,
    minute: int = 0,
    employee: str = "dev_1",
) -> Screenshot:
    return Screenshot(
        id=sid,
        path=Path(f"{sid}.png"),
        captured_at=datetime(2026, 4, 22, hour, minute, tzinfo=UTC),
        metadata=ScreenshotMetadata(employee_id=employee),
    )


def _cls(sid: str, activity: ActivityType) -> ClassificationResult:
    return ClassificationResult(
        screenshot_id=sid,
        activity_type=activity,
        category="x",
        evidence=("e",),
        confidence=0.9,
    )


def _state(
    screenshots: list[Screenshot],
    classifications: dict[str, ClassificationResult],
    tmp_path: Path,
) -> AgentState:
    return AgentState(
        input_dir=tmp_path,
        screenshots=screenshots,
        classifications=classifications,
    )


@pytest.mark.asyncio
class TestStaticRunDetection:
    async def test_static_run_detected(self, test_deps: Deps, tmp_path: Path) -> None:
        screenshots = [_ss(f"s{i}", 9, i * 5) for i in range(4)]
        classifications = {s.id: _cls(s.id, ActivityType.IDLE_STATIC) for s in screenshots}

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        assert len(result.timeline_patterns) == 1
        pattern = result.timeline_patterns[0]
        assert pattern.pattern == "long_static_period"
        assert pattern.risk_level == RiskLevel.MEDIUM
        assert pattern.requires_review is True
        assert pattern.employee_id == "dev_1"
        assert len(pattern.screenshot_ids) == 4

    async def test_static_run_below_threshold(
        self, test_deps: Deps, tmp_path: Path
    ) -> None:
        screenshots = [_ss(f"s{i}", 9, i * 5) for i in range(3)]
        classifications = {s.id: _cls(s.id, ActivityType.IDLE_STATIC) for s in screenshots}

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        assert result.timeline_patterns == []

    async def test_static_run_broken_by_other_category(
        self, test_deps: Deps, tmp_path: Path
    ) -> None:
        screenshots = [_ss(f"s{i}", 9, i * 5) for i in range(6)]
        classifications = {
            "s0": _cls("s0", ActivityType.IDLE_STATIC),
            "s1": _cls("s1", ActivityType.IDLE_STATIC),
            "s2": _cls("s2", ActivityType.PRODUCTIVE_WORK),
            "s3": _cls("s3", ActivityType.IDLE_STATIC),
            "s4": _cls("s4", ActivityType.IDLE_STATIC),
            "s5": _cls("s5", ActivityType.IDLE_STATIC),
        }

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        # Левый сегмент (2) ниже порога 4, правый (3) тоже ниже.
        assert result.timeline_patterns == []


@pytest.mark.asyncio
class TestJobSearchBurst:
    async def test_job_search_burst_detected(
        self, test_deps: Deps, tmp_path: Path
    ) -> None:
        screenshots = [_ss(f"j{i}", 14, i * 5) for i in range(3)]
        classifications = {
            s.id: _cls(s.id, ActivityType.JOB_SEARCH_SIGNAL) for s in screenshots
        }

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        bursts = [p for p in result.timeline_patterns if p.pattern == "job_search_burst"]
        assert len(bursts) == 1
        burst = bursts[0]
        assert burst.risk_level == RiskLevel.HIGH
        assert burst.requires_review is True
        assert len(burst.screenshot_ids) == 3

    async def test_job_search_burst_split_by_hour(
        self, test_deps: Deps, tmp_path: Path
    ) -> None:
        # 2 job_search в 14:55 и 2 в 15:05 — разные часы, ни один час не наберёт >=3.
        screenshots = [
            _ss("j1", 14, 50),
            _ss("j2", 14, 55),
            _ss("j3", 15, 5),
            _ss("j4", 15, 10),
        ]
        classifications = {
            s.id: _cls(s.id, ActivityType.JOB_SEARCH_SIGNAL) for s in screenshots
        }

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        bursts = [p for p in result.timeline_patterns if p.pattern == "job_search_burst"]
        assert bursts == []

    async def test_below_threshold(self, test_deps: Deps, tmp_path: Path) -> None:
        screenshots = [_ss(f"j{i}", 14, i * 5) for i in range(2)]
        classifications = {
            s.id: _cls(s.id, ActivityType.JOB_SEARCH_SIGNAL) for s in screenshots
        }

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        assert result.timeline_patterns == []


@pytest.mark.asyncio
class TestMultiEmployeeIsolation:
    async def test_two_employees_get_separate_patterns(
        self, test_deps: Deps, tmp_path: Path
    ) -> None:
        # У каждого сотрудника по 4 IDLE_STATIC скрина в одном и том же часу.
        dev1_shots = [_ss(f"a{i}", 9, i * 5, employee="dev_1") for i in range(4)]
        dev2_shots = [_ss(f"b{i}", 9, i * 5, employee="dev_2") for i in range(4)]
        screenshots = dev1_shots + dev2_shots
        classifications = {
            s.id: _cls(s.id, ActivityType.IDLE_STATIC) for s in screenshots
        }

        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, classifications, tmp_path))

        assert len(result.timeline_patterns) == 2
        employees = {p.employee_id for p in result.timeline_patterns}
        assert employees == {"dev_1", "dev_2"}

        # Скрины каждого сотрудника не пересекаются.
        all_ids: list[str] = []
        for p in result.timeline_patterns:
            all_ids.extend(p.screenshot_ids)
        assert len(all_ids) == len(set(all_ids))


@pytest.mark.asyncio
class TestEmptyInputs:
    async def test_no_screenshots(self, test_deps: Deps, tmp_path: Path) -> None:
        node = make_timeline_node(test_deps)
        result = await node(_state([], {}, tmp_path))
        assert result.timeline_patterns == []

    async def test_no_classifications(self, test_deps: Deps, tmp_path: Path) -> None:
        screenshots = [_ss(f"s{i}", 9, i * 5) for i in range(5)]
        node = make_timeline_node(test_deps)
        result = await node(_state(screenshots, {}, tmp_path))
        assert result.timeline_patterns == []
