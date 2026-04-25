# Архитектура

Документ будет дополнен по ходу реализации. Базовый референс — [план реализации](../). На этапе 0 — только скелет проекта.

## Высокоуровневая схема

```
┌──────────────┐
│  fixtures/   │  ← Скриншоты + manifest.yaml
│  data/       │     (ScreenshotMetadata)
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph Pipeline                           │
│                                                                     │
│  Collector → ImageRedaction → Vision → Classifier → Relevance →     │
│  → Timeline → Scoring → Reports                                     │
│                                                                     │
│  AgentState (pydantic, frozen) ─── checkpoint → SQLite              │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  Reports (output/)       │
│  ├── employee_*.json     │
│  ├── project_*.json      │
│  └── screenshot_table.md │
└──────────────────────────┘
```

## Слои (Hexagonal)

- `domain/` — доменные модели (pydantic), enum'ы, `Protocol`-порты. Без внешних зависимостей.
- `application/` — узлы LangGraph + use-case сервисы (risk_calculator, work_activity_calculator, timeline_grouper).
- `infrastructure/` — адаптеры портов (LiteLLM, Presidio, LocalFS, structlog).
- `presentation/` — CLI (typer).
- `config/` — pydantic-settings + DI-контейнер (`Deps` dataclass).

## Ключевые архитектурные решения

См. [docs/adr/](./adr/).
