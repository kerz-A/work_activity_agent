# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), проект следует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Added
- `Settings.redacted_dir` (env `REDACTED_DIR`) — явный override директории для редактированных копий скрин-шотов.
- `Settings.minutes_per_screenshot` (env `MINUTES_PER_SCREENSHOT`) — бизнес-параметр breakdown в отчётах.
- `_validate_thresholds()` — `RiskCalculator` и `WorkActivityCalculator` падают на init при `low >= medium` в конфиге.
- `_ensure_utf8_console()` в CLI — реконфигурирует stdout/stderr на utf-8 для Windows-cp1251.
- `tests/unit/presentation/test_cli.py` — 17 unit-тестов на `doctor` helpers, `version`, `validate-prompts`.
- Регрессионные тесты на `task_alignment` нормализацию и thresholds monotonicity.

### Changed
- **PERF**: `PresidioImageRedactor` кеширует `ImageAnalyzerEngine` как атрибут класса — раньше пересоздавался на каждый скрин (cold-start ~4s × N), теперь один раз на инстанс.
- **PERF**: `reports.py` — lift `screenshot_id` set из генератора фильтрации флагов (O(n·m) → O(n+m)).
- **PERF**: `risk_calculator._compute_components` — 5 проходов по списку слиты в один.
- **PERF**: `scoring.py` — `defaultdict(list)` для `timeline_patterns` lookup вместо linear filter в цикле.
- **FIX**: `task_alignment` нормализуется по числу скрин-шотов сотрудника, не по `len(relevances)` — раньше частичные оценки LLM могли давать ложную 1.0.
- **REFACTOR**: `cli.doctor()` разбит на `_check_python` / `_check_tesseract` / `_check_llm` / `_check_presidio` / `_check_spacy` / `_check_configs` (152 LOC → ~30 LOC главная + helper'ы).
- **REFACTOR**: `LiteLLMProvider._call_with_validation` разбит на `_network_call_with_timeout`, `_build_retry_messages`, `_track_cost_and_check_budget`. Поведение идентично.
- **SECURITY**: `_export_api_keys_to_env` экспортирует API-ключи в `os.environ` только для фактически используемых провайдеров (по `model_aliases`) — лишние секреты не утекают в дочерние процессы.
- **REFACTOR**: `cli._run_graph` — `assert isinstance(deps, Deps)` заменён явной `TypeError`; `log.exception` для сохранения traceback при pipeline-ошибках вместо truncate.
- **CLASSIFIER**: defensive `except Exception` в `_classify` с reraise для `LLMBudgetExceededError` — неожиданная ошибка одного скрина не валит весь `gather`.
- **COLLECTOR**: `_file_mtime_utc` обёрнут в `try/except OSError` с fallback на `datetime.now(UTC)`.
- Документация: расширены `docs/architecture.md` и `docs/prompts.md`. Поправлена doctor-таблица в `docs/runbook.md` (7 проверок, не 6) + Windows PowerShell команды cleanup.

### Fixed
- Утечка `PIL.Image` в `PresidioImageRedactor.redact` — `redacted_img` теперь явно закрывается через `try/finally`.
- Bare `except Exception` в `_analyze_metadata` без логирования — добавлен `log.warning` для сохранения сигнала о PII detection failure.
- `_file_mtime_utc` падал на битых симлинках — теперь graceful degradation.

### Tests
- 207 passed (было 187, +20 регрессионных и unit на CLI).

---

## Базовый цикл (до текущих фиксов)

### Added
- Базовый скелет проекта: pyproject.toml (uv), Makefile, pre-commit, GitHub Actions
- Структура папок по Hexagonal architecture (domain / application / infrastructure / presentation)
- 8-узловой LangGraph pipeline: Collector → ImageRedaction → Vision → Classifier → Relevance → Timeline → Scoring → Reports
- Domain-модели (pydantic), enum'ы, ports (Protocol)
- Infrastructure-адаптеры: LiteLLM (Ollama + Cloud), Presidio image redactor, regex text redactor, LocalFS storage, YAML manifest, JSON+Markdown report sinks
- Synthetic test data generators (Pillow + Playwright) и 68 fixture скрин-шотов
- Docker isolation: 3 профиля (`local-llm` / `host-llm` / `cloud-llm`) с GPU-overlay
- `doctor` команда — диагностика окружения
- Privacy strict mode + budget stop + concurrent semaphores
- Структурное логирование (structlog, JSON в проде)
- Документация: README, runbook, manifest spec, prompts guide, ADR-0001/0002/0003, LICENSE, examples

[Unreleased]: https://github.com/kerz-A/work_activity_agent/compare/main...HEAD
