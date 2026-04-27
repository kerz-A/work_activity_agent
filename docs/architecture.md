# Архитектура

Документ описывает текущее устройство `work-activity-agent`: слои, pipeline, контракты состояния и ключевые проектные решения.

## Содержание

1. [Слои (Hexagonal)](#слои-hexagonal)
2. [Pipeline](#pipeline)
3. [AgentState — единый контракт между узлами](#agentstate)
4. [Узлы — обязанности и контракты](#узлы)
5. [Ports & Adapters](#ports--adapters)
6. [Конфигурация](#конфигурация)
7. [Privacy и обработка PII](#privacy)
8. [Error handling](#error-handling)
9. [Производительность](#производительность)
10. [Архитектурные решения](#архитектурные-решения)

---

## Слои (Hexagonal)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        presentation/                                 │
│  CLI (typer): doctor, run, dry-run, validate-prompts, version        │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        application/                                  │
│  ┌──────────────┐  ┌────────────────────────────────────────┐        │
│  │ nodes/*.py   │→│ services/                                │        │
│  │ (LangGraph)  │  │   risk_calculator                       │        │
│  │              │  │   work_activity_calculator              │        │
│  │              │  │   timeline_grouper                      │        │
│  │              │  │   evidence_builder                      │        │
│  └──────────────┘  └────────────────────────────────────────┘        │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ через Protocol-порты
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        infrastructure/                               │
│  llm/litellm_provider     redaction/presidio_image_redactor          │
│  llm/fake_provider        redaction/regex_text_redactor              │
│  storage/local_fs         redaction/noop_redactor                    │
│  storage/manifest_yaml    reports/{json,markdown}_sink               │
│  prompts/filesystem_loader  observability/logging                    │
└──────────────────────────────────────────────────────────────────────┘
                             ▲
                             │ инжекция через DI
┌──────────────────────────────────────────────────────────────────────┐
│                        config/                                       │
│  Settings (pydantic-settings)   Deps (frozen dataclass)              │
└──────────────────────────────────────────────────────────────────────┘
                             ▲
┌──────────────────────────────────────────────────────────────────────┐
│                        domain/                                       │
│  models/*.py    enums    errors    ports/*.py (Protocol)             │
│  Без внешних зависимостей: только pydantic + stdlib                  │
└──────────────────────────────────────────────────────────────────────┘
```

Слой **domain** не импортирует ничего из других слоёв. **application** зависит только от `domain.ports` (Protocol), не от конкретных реализаций. **infrastructure** реализует порты. **presentation** и **config** склеивают всё вместе.

## Pipeline

LangGraph-граф: 8 узлов, последовательный (без conditional routing в MVP).

```
fixtures/screenshots/                  configs/
  manifest.yaml                          default.yaml      (веса/пороги)
       │                                 models.{profile}.yaml (alias→model)
       │                                 prompts/*.md
       ▼                                       │
┌──────────────┐                               │
│ Collector    │  чтение PNG + manifest        │
└──────┬───────┘                               │
       ▼                                       ▼
┌──────────────┐  ┌──────────────────────────────┐
│ ImageRedaction│ │  Presidio (Tesseract+spaCy)  │
│              │←│  закрашивает PII bbox-ами     │
└──────┬───────┘  └──────────────────────────────┘
       ▼
┌──────────────┐  ┌──────────────────────────────┐
│ Vision       │←─│ LLM: vision_describe         │ → VisionResult (visible_app, text, activity)
│ (gather, sem)│  └──────────────────────────────┘
└──────┬───────┘
       ▼
┌──────────────┐  ┌──────────────────────────────┐
│ Classifier   │←─│ LLM: classify_activity       │ → ClassificationResult (one of 11 categories)
│ (gather, sem)│  └──────────────────────────────┘
└──────┬───────┘
       ▼
┌──────────────┐  ┌──────────────────────────────┐
│ Relevance    │←─│ LLM: task_relevance          │ → RelevanceResult (high/medium/low/unclear)
│ (gather, sem)│  └──────────────────────────────┘
└──────┬───────┘
       ▼
┌──────────────┐
│ Timeline     │  детектирование паттернов (static_screen_long, job_search_burst…)
└──────┬───────┘
       ▼
┌──────────────┐
│ Scoring      │  RiskCalculator + WorkActivityCalculator (детерминистично)
└──────┬───────┘
       ▼
┌──────────────┐
│ Reports      │  Employee + Project + ScreenshotTable
└──────┬───────┘  через ReportSink-ы (JSON + Markdown)
       ▼
data/reports/
  employee_*.{json,md}
  project_*.{json,md}
  screenshots_table.{json,md}
```

**Ключевые свойства**:
- **Иммутабельный state**: каждый узел возвращает `state.model_copy(update=...)`. LangGraph контролирует transition.
- **Накопительность**: ошибки одного узла не валят следующий — пустой dict вместо crash.
- **Семафоры на LLM-узлах**: `Vision`, `Classifier`, `Relevance` дёргают LLM параллельно (asyncio.gather + semaphore из `LLM_MAX_CONCURRENT_VISION` или `classifier.max_concurrent`/`relevance.max_concurrent`).

## AgentState

Один pydantic-объект, передаётся между узлами. Полная сигнатура — `src/work_activity_agent/application/state.py`. Ключевое:

```python
class AgentState(BaseModel):
    # Вход
    input_dir: Path
    run_id: str             # uuid4()[:12]
    employee_filter: str | None
    date_filter: date | None

    # Накапливается узлами
    screenshots: list[Screenshot]                      # collector
    redacted_screenshots: dict[id, RedactedScreenshot] # image_redaction
    vision_results: dict[id, VisionResult]             # vision
    classifications: dict[id, ClassificationResult]    # classifier
    relevances: dict[id, RelevanceResult]              # relevance
    timeline_patterns: list[TimelinePattern]           # timeline
    risk_scores: dict[employee_date_key, RiskScore]    # scoring
    work_activity_scores: dict[employee_date_key, ...] # scoring

    # Финал
    employee_reports: list[EmployeeReport]             # reports
    project_reports: list[ProjectReport]
    screenshot_table: list[ScreenshotTableRow]

    errors: list[NodeError]   # неблокирующие ошибки
```

Ключевое решение: `dict[screenshot_id, ...]` для всех per-screenshot результатов даёт O(1) lookup в Reports/Scoring и устойчиво к выпадениям отдельных скринов.

## Узлы

| Узел | Файл | Async | LLM | Описание |
|---|---|:-:|:-:|---|
| Collector | `nodes/collector.py` | ❌ | ❌ | Читает PNG из `input_dir` через `ScreenshotStorage` port. Резолв `captured_at`: manifest → имя файла → mtime. |
| ImageRedaction | `nodes/image_redaction.py` | ❌ | ❌ | Через `ImageRedactor` port (Presidio): закрашивает PII, конвертирует в RGB, downscale до 1024px, сохраняет в `redacted_dir` (env-конфигурируемо). При `privacy_strict=True` ошибка редакции выкидывает скрин из pipeline; иначе — fallback на оригинал. |
| Vision | `nodes/vision.py` | ✅ | ✅ | Семафор `LLM_MAX_CONCURRENT_VISION`. Дёргает `vision_describe` промпт. Visible_text дополнительно прогоняется через `TextRedactor` (regex для PII, которое OCR пропустил). |
| Classifier | `nodes/classifier.py` | ✅ | ✅ | Семафор `classifier.max_concurrent`. Категоризация по 11 типам (см. `domain/enums.py: ActivityType`). При неуспехе → fallback `NEUTRAL_UNCLEAR` (не теряем скрин из знаменателя). |
| Relevance | `nodes/relevance.py` | ✅ | ✅ | Сравнивает activity со `tracked_task_title`. Skip если в manifest нет задачи (relevance остаётся пустым для этого скрина). |
| Timeline | `nodes/timeline.py` | ❌ | ❌ | Детерминистично детектит паттерны (`static_screen_long_period`, `job_search_burst`). Использует pHash для «одинаковых» скринов. |
| Scoring | `nodes/scoring.py` | ❌ | ❌ | `RiskCalculator` (7 компонентов, веса из `default.yaml`), `WorkActivityCalculator` (7 компонентов). Score 0-100, levels low/medium/high. Thresholds монотонность валидируется на init. |
| Reports | `nodes/reports.py` | ❌ | ❌ | Сборка `EmployeeReport`/`ProjectReport`/`ScreenshotTableRow` + запись через все `ReportSink`-ы (JSON + Markdown). |

Узлы в `application/nodes/` — это фабрики `make_<node>_node(deps: Deps) -> Callable[[AgentState], AgentState]`. DI через closure: deps инжектятся при сборке графа в `application/graph.py`, узел получает их через замыкание, не через state.

## Ports & Adapters

```
domain/ports/                           infrastructure/
  llm_provider.py            LiteLLMProvider (litellm + tenacity retry)
                             FakeLLMProvider (тесты, dry-run)

  image_redactor.py          PresidioImageRedactor (spaCy en_core_web_sm + Tesseract)
                             NoopImageRedactor    (тесты, dry-run)

  text_redactor.py           RegexTextRedactor (PII regex для visible_text)

  storage.py                 LocalFSStorage (файловая система)

  manifest_loader.py         YamlManifestLoader

  prompt_loader.py           FilesystemPromptLoader (configs/prompts/*.md + jinja2)

  report_sink.py             JsonReportSink + MarkdownReportSink
                             (две разные реализации, обе вызываются параллельно)
```

Все порты — `Protocol` (PEP 544), `runtime_checkable=False`. Узлы зависят только от Protocol, не от конкретных классов.

## Конфигурация

### Settings (pydantic-settings, env-driven)

| Группа | Префикс env | Откуда |
|---|---|---|
| `LLMSettings` | `LLM_` | `.env` или env переменные |
| `RiskSettings` | `RISK_` | `.env` + `configs/default.yaml` |
| `ObservabilitySettings` | `OBSERVABILITY_` | `.env` |
| Корневые | (без префикса) | `INPUT_DIR`, `OUTPUT_DIR`, `CHECKPOINT_DIR`, `REDACTED_DIR`, `MINUTES_PER_SCREENSHOT` |

Полный список env — `.env.example`.

### Конфигурации YAML

- **`configs/default.yaml`** — веса/пороги для RiskCalculator + WorkActivityCalculator + параметры Timeline/Vision/Classifier/Relevance.
- **`configs/models.local.yaml`** / **`models.cloud.yaml`** — alias→model. Резолв: `LLM_MODELS_CONFIG_PATH` → `models.{LLM_PROFILE}.yaml` → `models.yaml` (backward compat).
- **`configs/prompts/*.md`** — промпты с YAML frontmatter (см. [docs/prompts.md](prompts.md)).

### Deps (frozen dataclass)

`config/container.py: build_dependencies()` собирает все адаптеры под Settings и возвращает `Deps`. В тестах есть `use_fake_llm=True` и `use_noop_redactor=True` для построения тестового Deps без внешних зависимостей.

## Privacy

PII обрабатывается **до** Vision, по принципу defence-in-depth:

1. **ImageRedaction** (Presidio + Tesseract OCR) — закрашивает чёрными прямоугольниками distinguished entities на изображении ([ADR-0003](adr/0003-redaction-before-vision.md)).
2. **Vision** прогоняется по уже отредактированным копиям. Раньше Vision дойдёт до `Image.open(redacted)`, оригинал не отправляется.
3. **TextRedactor** (regex) — постобработка `VisionResult.visible_text` на случай если OCR пропустил что-то.
4. **Privacy strict mode** (`LLM_PRIVACY_STRICT=true` по умолчанию): при ошибке редакции скрин **отбрасывается**, не уходит в Vision.

Поддерживаемые типы PII (см. `domain/enums.py: SensitiveDataType`): EMAIL, PHONE, BANK_DETAILS (credit card / IBAN), PASSPORT (US passport / SSN), MEDICAL, THIRD_PARTY (PERSON entity).

## Error handling

| Уровень | Стратегия |
|---|---|
| Один скрин в Collector/ImageRedaction | warning + continue / drop в strict mode |
| Один скрин в LLM-узле | retry → fallback NEUTRAL_UNCLEAR (Classifier), skip (Relevance), drop (Vision) — записываем `NodeError` в state.errors |
| `LLMNetworkError` (timeout/HTTP/connection) | tenacity retry внутри `LiteLLMProvider`, потом наружу |
| `LLMResponseValidationError` (JSON/Pydantic) | self-healing retry с feedback в контексте, до 2 раз |
| `LLMBudgetExceededError` (cloud) | прерывает graceful: уже сделанные результаты сохраняются, экранам после — fallback. Reports пишутся на partial state |
| Unexpected `Exception` в gather | defensive `except Exception` в каждом `_classify`/`_process` — не валит весь батч |

В Reports попадают **все** скрины, даже с пустой классификацией — иначе знаменатель в Risk/WorkActivity ломался бы.

## Производительность

| Этап | Алгоритмическая сложность | LLM нагрузка |
|---|---|---|
| Collector | O(N) | — |
| ImageRedaction | O(N), spaCy/Tesseract на CPU | — (Presidio singleton — кешируется на инстанс) |
| Vision | O(N) последовательно с семафором | N запросов |
| Classifier | O(N) | N запросов |
| Relevance | O(N_with_task) | до N запросов |
| Timeline | O(N log N) — сортировка, sliding window для bursts | — |
| Scoring | O(N + employees) — один проход | — |
| Reports | O(N + employees + projects) | — |

LLM-вызовы — единственное «дорогое» место. На 68 скринах: Vision (10-15 мин на GTX 1660) + Classifier (5-7 мин) + Relevance (3-5 мин) ≈ 20-25 минут. Cloud в 2-4 раза быстрее.

Для cold-start Presidio есть критичный фикс: `ImageAnalyzerEngine` кешируется как атрибут класса при первом вызове `redact()`. Раньше пересоздавался на каждый скрин и съедал ~4с/скрин.

## Архитектурные решения

Подробно — [`docs/adr/`](adr/):

- [ADR-0001](adr/0001-langgraph.md) — Почему LangGraph, а не просто chain функций.
- [ADR-0002](adr/0002-litellm.md) — Почему LiteLLM как единая точка интеграции.
- [ADR-0003](adr/0003-redaction-before-vision.md) — Почему image redaction до Vision (а не после).

## Что снаружи pipeline

- `tools/` — генераторы синтетических данных (Pillow + Playwright).
- `mocks/` — HTML-моки для `tools/capture_html_mocks.py`.
- `fixtures/` — 68 готовых скрин-шотов по 11 категориям + manifest.yaml.
- `examples/` — sample input + sample output для презентаций.
- `tests/` — `unit/` (по слоям) + `integration/` (LangGraph happy path с FakeLLM).
