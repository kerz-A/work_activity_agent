"""Тесты ClassificationResult, RelevanceResult."""

import pytest
from pydantic import ValidationError

from work_activity_agent.domain.enums import ActivityType, RelevanceLevel, RiskFlagType
from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)


class TestClassificationResult:
    def test_minimal_valid(self) -> None:
        r = ClassificationResult(
            screenshot_id="scr_1",
            activity_type=ActivityType.PRODUCTIVE_WORK,
            category="software_development",
            evidence=("VS Code открыт",),
            confidence=0.82,
        )
        assert r.activity_type == ActivityType.PRODUCTIVE_WORK

    def test_evidence_must_have_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(
                screenshot_id="scr_1",
                activity_type=ActivityType.PRODUCTIVE_WORK,
                category="software_development",
                evidence=(),
                confidence=0.82,
            )

    def test_evidence_capped_at_10(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(
                screenshot_id="scr_1",
                activity_type=ActivityType.PRODUCTIVE_WORK,
                category="software_development",
                evidence=tuple(f"e{i}" for i in range(11)),
                confidence=0.82,
            )


class TestRelevanceResult:
    def test_unclear_when_no_task(self) -> None:
        r = RelevanceResult(
            screenshot_id="scr_1",
            tracked_task=None,
            screenshot_activity="editing code",
            relevance=RelevanceLevel.UNCLEAR,
            confidence=0.5,
        )
        assert r.tracked_task is None
        assert r.relevance == RelevanceLevel.UNCLEAR

    def test_with_risk_flag(self) -> None:
        r = RelevanceResult(
            screenshot_id="scr_1",
            tracked_task="design cart",
            screenshot_activity="job search site",
            relevance=RelevanceLevel.LOW,
            risk_flags=(RiskFlagType.JOB_SEARCH_SITE,),
            confidence=0.78,
            note="Фиксируется только видимый факт",
        )
        assert RiskFlagType.JOB_SEARCH_SITE in r.risk_flags
