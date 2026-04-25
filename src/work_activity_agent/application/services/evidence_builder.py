"""EvidenceBuilder — собирает RiskFlag'и + EvidenceLink'и из паттернов и relevance."""

from __future__ import annotations

from collections.abc import Sequence

from work_activity_agent.domain.enums import RiskFlagType, RiskLevel
from work_activity_agent.domain.models.classification import RelevanceResult
from work_activity_agent.domain.models.reports import EvidenceLink
from work_activity_agent.domain.models.risk import RiskFlag, TimeInterval, TimelinePattern
from work_activity_agent.domain.models.screenshot import Screenshot

# Маппинг pattern → RiskFlagType
_PATTERN_TO_FLAG: dict[str, RiskFlagType] = {
    "long_static_period": RiskFlagType.STATIC_SCREEN_LONG_PERIOD,
    "job_search_burst": RiskFlagType.JOB_SEARCH_SITE,
}


class EvidenceBuilder:
    """Собирает RiskFlag из TimelinePattern и RelevanceResult."""

    def build_flags(
        self,
        patterns: Sequence[TimelinePattern],
        relevances: dict[str, RelevanceResult],
        screenshots_by_id: dict[str, Screenshot],
    ) -> list[RiskFlag]:
        flags: list[RiskFlag] = []
        flags.extend(self._flags_from_patterns(patterns))
        flags.extend(self._flags_from_relevance(relevances, screenshots_by_id))
        return flags

    def build_evidence_links(
        self,
        flags: Sequence[RiskFlag],
        screenshots_by_id: dict[str, Screenshot],
    ) -> list[EvidenceLink]:
        links: list[EvidenceLink] = []
        seen: set[str] = set()
        for flag in flags:
            for sid in flag.screenshot_ids:
                if sid in seen:
                    continue
                seen.add(sid)
                shot = screenshots_by_id.get(sid)
                if shot is None:
                    continue
                links.append(
                    EvidenceLink(
                        screenshot_id=sid,
                        path=shot.path,
                        caption=f"{flag.type.value}: {flag.evidence}",
                    )
                )
        return links

    @staticmethod
    def _flags_from_patterns(patterns: Sequence[TimelinePattern]) -> list[RiskFlag]:
        flags: list[RiskFlag] = []
        for p in patterns:
            flag_type = _PATTERN_TO_FLAG.get(p.pattern, RiskFlagType.MANUAL_REVIEW_REQUIRED)
            flags.append(
                RiskFlag(
                    type=flag_type,
                    interval=p.interval,
                    severity=p.risk_level,
                    evidence=p.reason,
                    screenshot_ids=p.screenshot_ids,
                    requires_human_review=p.requires_review,
                )
            )
        return flags

    @staticmethod
    def _flags_from_relevance(
        relevances: dict[str, RelevanceResult],
        screenshots_by_id: dict[str, Screenshot],
    ) -> list[RiskFlag]:
        flags: list[RiskFlag] = []
        for sid, rel in relevances.items():
            if not rel.risk_flags:
                continue
            shot = screenshots_by_id.get(sid)
            if shot is None:
                continue
            for flag_type in rel.risk_flags:
                flags.append(
                    RiskFlag(
                        type=flag_type,
                        interval=TimeInterval(start=shot.captured_at, end=shot.captured_at),
                        severity=RiskLevel.MEDIUM,
                        evidence=rel.note or f"Detected {flag_type.value} in screenshot",
                        screenshot_ids=(sid,),
                        requires_human_review=True,
                    )
                )
        return flags
