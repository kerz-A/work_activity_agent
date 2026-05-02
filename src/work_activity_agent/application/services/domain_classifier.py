"""DomainClassifier — детерминистичная классификация по OCR-тексту.

Применяет regex-правила (из configs/domain_rules.yaml) к сырому OCR-выводу
Tesseract и возвращает структурированные сигналы: домен, категория домена,
тип страницы, тип приложения. Используется узлом ocr_signals — без LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from work_activity_agent.domain.models.ocr_signals import AppKind, OCRSignals

# Универсальный URL-регекс. Не ловит TLDы экзотические — но для скринов
# из таск-трекеров достаточно общих доменов.
_URL_RE = re.compile(
    r"(?:https?://|www\.)?([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"
    r"\.(?:ru|com|org|net|io|co|me|tv|us|tech|dev|info|edu|gov))(?:/[^\s\"\'<>]*)?",
    re.IGNORECASE,
)

# Типичные суффиксы заголовков вкладок браузера: "<title> - <browser>"
_TAB_TITLE_RE = re.compile(
    r"(.{3,120}?)\s*[—\-–]\s*(?:Yandex|Yandex Browser|Google Chrome|Chrome|Mozilla Firefox|"
    r"Firefox|Microsoft Edge|Edge|Opera|Safari)",
    re.IGNORECASE,
)


def _flatten_text(raw_text: Iterable[str]) -> str:
    """Сложить OCR-вывод в одну строку для regex-поиска (с разделителем)."""
    return "\n".join(s for s in raw_text if s)


class DomainClassifier:
    """Применяет правила из domain_rules.yaml к OCR-тексту скрина."""

    # Минимум content-keyword попаданий для классификации по контенту.
    # 2+ — снижает ложные срабатывания на одиночное случайное слово.
    _CONTENT_KEYWORD_MIN_HITS = 2

    # Категории, content-маркеры которых перебивают любую domain-категорию.
    # job_search особенно: вакансию могут просматривать на github.com
    # (тестовое задание для устройства) — domain даст productive_dev,
    # но контент явно job_search.
    _CONTENT_OVERRIDE_CATEGORIES = frozenset({"job_search", "entertainment"})

    # Fallback domain_category из app_kind, когда domain не определён.
    _APP_KIND_TO_CATEGORY: dict[str, str] = {
        "ide": "productive_dev",
        "office": "productive_office",
        "messenger": "productive_communication",
    }

    def __init__(
        self,
        domain_categories: Mapping[str, list[str]],
        page_kinds: list[Mapping[str, str]],
        app_markers: Mapping[str, list[str]],
        content_keywords: Mapping[str, list[str]] | None = None,
        strong_keywords: Mapping[str, list[str]] | None = None,
    ) -> None:
        # domain → category (плоский reverse-индекс для быстрого lookup)
        self._domain_to_category: dict[str, str] = {}
        for category, domains in domain_categories.items():
            for d in domains:
                self._domain_to_category[d.lower()] = category

        # компилируем regex для page_kinds один раз
        self._page_kind_rules: list[tuple[re.Pattern[str], str]] = [
            (re.compile(rule["pattern"], re.IGNORECASE), rule["kind"]) for rule in page_kinds
        ]

        # маркеры в lower-case для быстрого `in`
        self._app_markers: dict[str, list[str]] = {
            kind: [m.lower() for m in markers] for kind, markers in app_markers.items()
        }

        # content-keyword fallback (по категориям)
        self._content_keywords: dict[str, list[str]] = {
            cat: [k.lower() for k in keywords]
            for cat, keywords in (content_keywords or {}).items()
        }
        # strong keywords: 1 попадание достаточно (для очень специфичных фраз)
        self._strong_keywords: dict[str, list[str]] = {
            cat: [k.lower() for k in keywords]
            for cat, keywords in (strong_keywords or {}).items()
        }

    @classmethod
    def from_yaml(cls, path: Path) -> DomainClassifier:
        """Загрузить правила из YAML-файла."""
        if not path.exists():
            raise FileNotFoundError(f"domain rules config not found: {path}")
        with path.open(encoding="utf-8") as f:
            data: Any = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"domain rules config must be a dict, got {type(data).__name__}")
        return cls(
            domain_categories=data.get("domain_categories", {}),
            page_kinds=data.get("page_kinds", []),
            app_markers=data.get("app_markers", {}),
            content_keywords=data.get("content_keywords", {}),
            strong_keywords=data.get("strong_keywords", {}),
        )

    def classify(self, screenshot_id: str, raw_text: tuple[str, ...]) -> OCRSignals:
        """Применить все правила к OCR-тексту и вернуть OCRSignals."""
        flat = _flatten_text(raw_text)
        flat_lower = flat.lower()

        domain, full_url = self._extract_domain(flat)
        domain_category = self._classify_domain(domain) if domain else None
        page_kind = self._classify_page_kind(full_url) if full_url else None
        app_kind = self._classify_app_kind(flat_lower)
        tab_titles = self._extract_tab_titles(flat)

        # Content-классификация: проверяем ВСЕГДА, даже если domain дал категорию.
        # Для job_search/entertainment контент перебивает domain (тестовое
        # задание на github → job_search, не productive_dev).
        content_category = self._classify_by_content(flat_lower)
        if content_category in self._CONTENT_OVERRIDE_CATEGORIES:
            domain_category = content_category
        elif domain_category is None and content_category is not None:
            domain_category = content_category

        # Fallback: app_kind → category, если domain так и остался None.
        if domain_category is None and app_kind is not None:
            domain_category = self._APP_KIND_TO_CATEGORY.get(app_kind)

        return OCRSignals(
            screenshot_id=screenshot_id,
            raw_text=raw_text,
            detected_domain=domain,
            domain_category=domain_category,
            detected_page_kind=page_kind,
            detected_app_kind=app_kind,
            tab_titles=tab_titles,
        )

    def _classify_by_content(self, text_lower: str) -> str | None:
        """Fallback: классифицировать по характерным фразам в OCR-тексте.

        Сначала проверяем strong_keywords (1 hit достаточно для очень специфичных
        фраз вроде "тестовое задание"). Если ни одной не нашли — переходим к
        обычным content_keywords с порогом CONTENT_KEYWORD_MIN_HITS.
        """
        # Strong: 1 попадание достаточно — semantically unambiguous фразы.
        for category, keywords in self._strong_keywords.items():
            for kw in keywords:
                if kw and kw in text_lower:
                    return category

        # Обычные content_keywords с порогом 2+
        best_category: str | None = None
        best_hits = 0
        for category, keywords in self._content_keywords.items():
            hits = sum(1 for kw in keywords if kw and kw in text_lower)
            if hits >= self._CONTENT_KEYWORD_MIN_HITS and hits > best_hits:
                best_category = category
                best_hits = hits
        return best_category

    def _extract_domain(self, text: str) -> tuple[str | None, str | None]:
        """Найти первый известный домен из домен-листа в тексте.

        Возвращает (домен, полный найденный URL).
        Приоритет — у доменов из конфига (известные сервисы), а не первого попавшегося.
        """
        text_lower = text.lower()
        # Сначала ищем известные домены — они приоритетнее случайных URL.
        for domain in self._domain_to_category:
            if domain in text_lower:
                # Попробуем найти полный URL вокруг этого домена для page_kind анализа.
                idx = text_lower.find(domain)
                # Берём слово целиком
                start = idx
                while start > 0 and text[start - 1] not in " \n\t\"'<>":
                    start -= 1
                end = idx + len(domain)
                while end < len(text) and text[end] not in " \n\t\"'<>":
                    end += 1
                return domain, text[start:end]

        # Иначе — общий regex (любой URL)
        m = _URL_RE.search(text)
        if m:
            return m.group(1).lower(), m.group(0)
        return None, None

    def _classify_domain(self, domain: str) -> str | None:
        """Найти категорию для домена (с учётом subdomain matching)."""
        domain_lower = domain.lower()
        # Точное совпадение
        if domain_lower in self._domain_to_category:
            return self._domain_to_category[domain_lower]
        # Subdomain match — например, "career.habr.com" ∈ известный "habr.com/career"?
        # Делаем suffix-match: domain заканчивается на ".<known>"
        for known, category in self._domain_to_category.items():
            if "/" in known:
                continue  # path-патрерн обрабатывается в page_kind
            if domain_lower.endswith("." + known) or domain_lower == known:
                return category
        return None

    def _classify_page_kind(self, full_url: str) -> str | None:
        """Применить regex-правила к URL → page_kind."""
        for pattern, kind in self._page_kind_rules:
            if pattern.search(full_url):
                return kind
        return None

    def _classify_app_kind(self, text_lower: str) -> AppKind | None:
        """Эвристика типа приложения по наличию характерных текстов."""
        # Сильнейший сигнал — прямой маркер в OCR
        for kind_specific, markers in self._app_markers.items():
            for marker in markers:
                if marker in text_lower:
                    return _normalize_app_kind(kind_specific)
        return None

    def _extract_tab_titles(self, text: str) -> tuple[str, ...]:
        """Найти заголовки вкладок (паттерн '<title> - <browser>')."""
        titles: list[str] = []
        for m in _TAB_TITLE_RE.finditer(text):
            title = m.group(1).strip()
            if title and title not in titles:
                titles.append(title)
            if len(titles) >= 5:
                break
        return tuple(titles)


def _normalize_app_kind(specific_kind: str) -> AppKind:
    """Свернуть специфичные подкатегории в AppKind enum."""
    if specific_kind == "ide":
        return "ide"
    if specific_kind == "browser":
        return "browser"
    if specific_kind.startswith("messenger_"):
        return "messenger"
    if specific_kind.startswith("office_") or specific_kind.startswith("google_"):
        return "office"
    return cast(AppKind, "other")
