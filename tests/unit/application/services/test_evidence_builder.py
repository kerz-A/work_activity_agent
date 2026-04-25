"""Тесты EvidenceBuilder."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from work_activity_agent.application.services.evidence_builder import EvidenceBuilder
from work_activity_agent.domain.enums import (
    RelevanceLevel,
    RiskFlagType,
    RiskLevel,
)
from work_activity_agent.domain.models.classification import RelevanceResult
from work_activity_agent.domain.models.risk import TimeInterval, TimelinePattern
from work_activity_agent.domain.models.screenshot import Screenshot


def _ss(sid: str, hour: int) -> Screenshot:
    return Screenshot(
        id=sid,
        path=Path(f"{sid}.png"),
        captured_at=datetime(2026, 4, 22, hour, 0, tzinfo=UTC),
    )


class TestBuildFlagsFromPatterns:
    def test_static_pattern_to_flag(self) -> None:
        pattern = TimelinePattern(
            employee_id="dev_1",
            interval=TimeInterval(
                start=datetime(2026, 4, 22, 14, 20, tzinfo=UTC),
                end=datetime(2026, 4, 22, 14, 50, tzinfo=UTC),
            ),
            pattern="long_static_period",
            risk_level=RiskLevel.MEDIUM,
            reason="Экран не менялся",
            requires_review=True,
            screenshot_ids=("s1", "s2", "s3"),
        )
        flags = EvidenceBuilder().build_flags([pattern], {}, {})
        assert len(flags) == 1
        assert flags[0].type == RiskFlagType.STATIC_SCREEN_LONG_PERIOD
        assert flags[0].requires_human_review is True

    def test_unknown_pattern_to_manual_review(self) -> None:
        pattern = TimelinePattern(
            employee_id="dev_1",
            interval=TimeInterval(
                start=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
                end=datetime(2026, 4, 22, 9, 30, tzinfo=UTC),
            ),
            pattern="some_unknown_pattern",
            risk_level=RiskLevel.MEDIUM,
            reason="?",
            requires_review=True,
            screenshot_ids=("s1",),
        )
        flags = EvidenceBuilder().build_flags([pattern], {}, {})
        assert flags[0].type == RiskFlagType.MANUAL_REVIEW_REQUIRED


class TestBuildFlagsFromRelevance:
    def test_relevance_with_risk_flags(self) -> None:
        rel = RelevanceResult(
            screenshot_id="s1",
            tracked_task="design cart",
            screenshot_activity="hh.ru",
            relevance=RelevanceLevel.LOW,
            risk_flags=(RiskFlagType.JOB_SEARCH_SITE,),
            confidence=0.8,
        )
        screenshot = _ss("s1", 16)
        flags = EvidenceBuilder().build_flags([], {"s1": rel}, {"s1": screenshot})
        assert len(flags) == 1
        assert flags[0].type == RiskFlagType.JOB_SEARCH_SITE

    def test_relevance_no_flags(self) -> None:
        rel = RelevanceResult(
            screenshot_id="s1",
            tracked_task="t",
            screenshot_activity="x",
            relevance=RelevanceLevel.HIGH,
            confidence=0.9,
        )
        screenshot = _ss("s1", 9)
        flags = EvidenceBuilder().build_flags([], {"s1": rel}, {"s1": screenshot})
        assert flags == []


class TestEvidenceLinks:
    def test_dedupes_screenshot_ids(self) -> None:
        screenshot = _ss("s1", 9)
        # Создадим два флага на один и тот же скриншот
        flag1 = EvidenceBuilder().build_flags(
            [
                TimelinePattern(
                    employee_id="dev_1",
                    interval=TimeInterval(
                        start=screenshot.captured_at,
                        end=screenshot.captured_at + timedelta(minutes=30),
                    ),
                    pattern="long_static_period",
                    risk_level=RiskLevel.MEDIUM,
                    reason="x",
                    requires_review=True,
                    screenshot_ids=("s1",),
                ),
            ],
            {
                "s1": RelevanceResult(
                    screenshot_id="s1",
                    tracked_task="t",
                    screenshot_activity="x",
                    relevance=RelevanceLevel.LOW,
                    risk_flags=(RiskFlagType.JOB_SEARCH_SITE,),
                    confidence=0.8,
                ),
            },
            {"s1": screenshot},
        )
        links = EvidenceBuilder().build_evidence_links(flag1, {"s1": screenshot})
        assert len(links) == 1  # дедупликация
