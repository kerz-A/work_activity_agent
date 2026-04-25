"""Тесты enum'ов: проверяем целостность с ТЗ — все категории и флаги на месте."""

from work_activity_agent.domain.enums import (
    ActivityType,
    RedactionAction,
    RelevanceLevel,
    RiskFlagType,
    RiskLevel,
    SensitiveDataType,
    WorkActivityLevel,
)


class TestActivityType:
    def test_has_eleven_categories_from_tech_spec(self) -> None:
        # ТЗ §3 — ровно 11 категорий
        assert len(ActivityType) == 11

    def test_string_values_match_snake_case(self) -> None:
        for member in ActivityType:
            assert member.value == member.name.lower()

    def test_no_duplicates(self) -> None:
        values = [m.value for m in ActivityType]
        assert len(values) == len(set(values))

    def test_required_categories_present(self) -> None:
        required = {
            "productive_work",
            "project_communication",
            "research",
            "admin_work",
            "neutral_unclear",
            "idle_static",
            "non_work",
            "job_search_signal",
            "other_project_signal",
            "sensitive_private",
            "needs_human_review",
        }
        actual = {m.value for m in ActivityType}
        assert actual == required


class TestRiskFlagType:
    def test_has_ten_flags_from_tech_spec(self) -> None:
        # ТЗ §4 — ровно 10 флагов
        assert len(RiskFlagType) == 10

    def test_required_flags_present(self) -> None:
        required = {
            "static_screen_long_period",
            "unrelated_website",
            "job_search_site",
            "freelance_platform",
            "other_project_tool",
            "personal_messenger",
            "entertainment_content",
            "low_task_relevance",
            "sensitive_data_detected",
            "manual_review_required",
        }
        actual = {m.value for m in RiskFlagType}
        assert actual == required


class TestRelevanceLevel:
    def test_has_four_levels(self) -> None:
        assert {m.value for m in RelevanceLevel} == {"high", "medium", "low", "unclear"}


class TestRiskLevel:
    def test_has_three_levels(self) -> None:
        assert {m.value for m in RiskLevel} == {"low", "medium", "high"}


class TestWorkActivityLevel:
    def test_has_three_levels(self) -> None:
        assert {m.value for m in WorkActivityLevel} == {"low", "medium", "high"}


class TestSensitiveDataType:
    def test_required_pii_types_present(self) -> None:
        # ТЗ §3 — Sensitive Data Redaction Agent
        required = {
            "email",
            "phone",
            "passport",
            "bank_details",
            "token",
            "password",
            "private_key",
            "private_chat",
            "medical",
            "client_document",
            "third_party",
        }
        actual = {m.value for m in SensitiveDataType}
        assert actual == required


class TestRedactionAction:
    def test_has_three_actions(self) -> None:
        assert {m.value for m in RedactionAction} == {
            "mask_before_report",
            "drop",
            "keep",
        }
