"""Smoke-тесты DomainClassifier — детерминистичная классификация по OCR-тексту."""

from pathlib import Path

import pytest

from work_activity_agent.application.services.domain_classifier import DomainClassifier


@pytest.fixture
def classifier() -> DomainClassifier:
    return DomainClassifier.from_yaml(Path("configs/domain_rules.yaml"))


class TestDomainDetection:
    def test_detects_hh_ru_as_job_search(self, classifier: DomainClassifier) -> None:
        text = (
            "Senior ML Engineer",
            "Откликнуться",
            "https://hh.ru/search/vacancy?text=python",
            "AI разработчик Python Junior/Middle",
        )
        result = classifier.classify("test_hh", text)
        assert result.detected_domain == "hh.ru"
        assert result.domain_category == "job_search"
        assert result.detected_page_kind == "vacancy_list"

    def test_detects_youtube_as_entertainment(self, classifier: DomainClassifier) -> None:
        text = (
            "YouTube",
            "Phonk Mix 2025",
            "youtube.com",
            "Я ВЕРНУЛСЯ FIBA3x3",
        )
        result = classifier.classify("test_yt", text)
        assert result.detected_domain == "youtube.com"
        assert result.domain_category == "entertainment"
        assert result.detected_page_kind == "video_feed"

    def test_detects_github_repo_as_productive_dev(self, classifier: DomainClassifier) -> None:
        text = (
            "Project — Internal Backend",
            "github.com/myorg/backend",
            "Code  Issues  Pull requests",
        )
        result = classifier.classify("test_gh", text)
        assert result.detected_domain == "github.com"
        assert result.domain_category == "productive_dev"
        assert result.detected_page_kind == "repository"

    def test_github_test_task_overrides_to_job_search(self, classifier: DomainClassifier) -> None:
        """Если в репо упоминается 'тестовое задание' — это сигнал поиска работы,
        даже если домен github.com (productive_dev). Strong keyword override."""
        text = (
            "Orders Dashboard — тестовое задание AI Tools Specialist",
            "github.com/user/dashboard_test",
            "Code  Issues  Pull requests",
        )
        result = classifier.classify("test_gh_test_task", text)
        assert result.detected_domain == "github.com"
        assert result.domain_category == "job_search"

    def test_detects_google_docs_as_productive_office(self, classifier: DomainClassifier) -> None:
        text = (
            "Техническое задание - Google Документы",
            "docs.google.com/document/d/abc123/edit",
            "4. Основные механики приложения",
        )
        result = classifier.classify("test_gd", text)
        assert result.detected_domain == "docs.google.com"
        assert result.domain_category == "productive_office"
        assert result.detected_page_kind == "document_edit"

    def test_no_domain_returns_none(self, classifier: DomainClassifier) -> None:
        text = ("Просто текст без URL", "ничего интересного")
        result = classifier.classify("test_empty", text)
        assert result.detected_domain is None
        assert result.domain_category is None


class TestAppKindDetection:
    def test_detects_messenger_discord(self, classifier: DomainClassifier) -> None:
        text = (
            "Discord",
            "ДОЖИ Медиа",
            "Информация о проекте",
            "Доступные роли",
        )
        result = classifier.classify("test_disc", text)
        assert result.detected_app_kind == "messenger"

    def test_detects_office_excel(self, classifier: DomainClassifier) -> None:
        text = (
            "Microsoft Excel",
            "Книга1 - Excel",
            "Формулы",
            "А1 fx",
        )
        result = classifier.classify("test_xl", text)
        assert result.detected_app_kind == "office"


class TestTabTitles:
    def test_extracts_browser_tab_title(self, classifier: DomainClassifier) -> None:
        text = (
            "Техническое задание - Google Chrome",
            "Yandex - вкладка",
        )
        result = classifier.classify("test_tabs", text)
        assert "Техническое задание" in result.tab_titles
