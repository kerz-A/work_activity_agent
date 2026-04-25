"""Тесты WorkActivityScore, ActivityComponents."""

from datetime import date

import pytest
from pydantic import ValidationError

from work_activity_agent.domain.enums import WorkActivityLevel
from work_activity_agent.domain.models.productivity import (
    ActivityComponents,
    WorkActivityScore,
)


class TestActivityComponents:
    def test_default_zeros(self) -> None:
        c = ActivityComponents()
        assert c.task_alignment == 0.0
        assert c.result_evidence == 0.0

    def test_values_must_be_in_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            ActivityComponents(task_alignment=1.5)
        with pytest.raises(ValidationError):
            ActivityComponents(task_alignment=-0.1)


class TestWorkActivityScore:
    def test_valid(self) -> None:
        s = WorkActivityScore(
            employee_id="dev_1",
            date=date(2026, 4, 22),
            score=72,
            level=WorkActivityLevel.HIGH,
            components=ActivityComponents(task_alignment=0.85, screen_dynamics=0.7),
            note="result_evidence не учтён (нет Git/Jira)",
        )
        assert s.score == 72
        assert s.level == WorkActivityLevel.HIGH

    def test_score_clamped_to_100(self) -> None:
        with pytest.raises(ValidationError):
            WorkActivityScore(
                employee_id="dev_1",
                date=date(2026, 4, 22),
                score=101,
                level=WorkActivityLevel.HIGH,
                components=ActivityComponents(),
            )
