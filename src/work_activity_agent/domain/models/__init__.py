"""Pydantic-модели домена."""

from work_activity_agent.domain.models.classification import (
    ClassificationResult,
    RelevanceResult,
)
from work_activity_agent.domain.models.productivity import (
    ActivityComponents,
    WorkActivityScore,
)
from work_activity_agent.domain.models.reports import (
    ActivityBreakdown,
    EmployeeReport,
    EvidenceLink,
    ProjectReport,
    ScreenshotTableRow,
)
from work_activity_agent.domain.models.risk import (
    RiskFlag,
    RiskScore,
    TimeInterval,
    TimelinePattern,
)
from work_activity_agent.domain.models.screenshot import (
    RedactedScreenshot,
    Screenshot,
    ScreenshotMetadata,
)
from work_activity_agent.domain.models.vision import (
    ExtractedMetadata,
    RedactionResult,
    VisionResult,
)

__all__ = [
    "ActivityBreakdown",
    "ActivityComponents",
    "ClassificationResult",
    "EmployeeReport",
    "EvidenceLink",
    "ExtractedMetadata",
    "ProjectReport",
    "RedactedScreenshot",
    "RedactionResult",
    "RelevanceResult",
    "RiskFlag",
    "RiskScore",
    "Screenshot",
    "ScreenshotMetadata",
    "ScreenshotTableRow",
    "TimeInterval",
    "TimelinePattern",
    "VisionResult",
    "WorkActivityScore",
]
