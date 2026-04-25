"""Доменные enum'ы. Соответствуют категориям и флагам из ТЗ §3, §4."""

from enum import StrEnum


class ActivityType(StrEnum):
    """11 категорий активности (ТЗ §3)."""

    PRODUCTIVE_WORK = "productive_work"
    PROJECT_COMMUNICATION = "project_communication"
    RESEARCH = "research"
    ADMIN_WORK = "admin_work"
    NEUTRAL_UNCLEAR = "neutral_unclear"
    IDLE_STATIC = "idle_static"
    NON_WORK = "non_work"
    JOB_SEARCH_SIGNAL = "job_search_signal"
    OTHER_PROJECT_SIGNAL = "other_project_signal"
    SENSITIVE_PRIVATE = "sensitive_private"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class RelevanceLevel(StrEnum):
    """Соответствие активности задаче (ТЗ §22.10)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCLEAR = "unclear"


class RiskFlagType(StrEnum):
    """10 типов risk flags (ТЗ §4)."""

    STATIC_SCREEN_LONG_PERIOD = "static_screen_long_period"
    UNRELATED_WEBSITE = "unrelated_website"
    JOB_SEARCH_SITE = "job_search_site"
    FREELANCE_PLATFORM = "freelance_platform"
    OTHER_PROJECT_TOOL = "other_project_tool"
    PERSONAL_MESSENGER = "personal_messenger"
    ENTERTAINMENT_CONTENT = "entertainment_content"
    LOW_TASK_RELEVANCE = "low_task_relevance"
    SENSITIVE_DATA_DETECTED = "sensitive_data_detected"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class RiskLevel(StrEnum):
    """Уровень риска для эпизодов и итогового скоринга."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkActivityLevel(StrEnum):
    """Уровень продуктивности (Work Activity Score)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SensitiveDataType(StrEnum):
    """Типы чувствительных данных (ТЗ §3 — Sensitive Data Redaction Agent)."""

    EMAIL = "email"
    PHONE = "phone"
    PASSPORT = "passport"
    BANK_DETAILS = "bank_details"
    TOKEN = "token"  # noqa: S105 — это enum значение, не реальный токен
    PASSWORD = "password"  # noqa: S105 — это enum значение, не реальный пароль
    PRIVATE_KEY = "private_key"
    PRIVATE_CHAT = "private_chat"
    MEDICAL = "medical"
    CLIENT_DOCUMENT = "client_document"
    THIRD_PARTY = "third_party"


class RedactionAction(StrEnum):
    """Что делать с обнаруженным чувствительным контентом."""

    MASK_BEFORE_REPORT = "mask_before_report"
    DROP = "drop"
    KEEP = "keep"
