# Тестовые фикстуры

Синтетические тестовые данные для агента. Все скриншоты — **синтетические**, реальных PII не содержат.

## Структура

```
fixtures/
├── screenshots/
│   ├── productive/        # Pillow placeholder PNG (Level 1)
│   ├── communication/
│   ├── research/
│   ├── admin/
│   ├── neutral/
│   ├── non_work/
│   ├── job_search/
│   ├── other_project/
│   ├── sensitive/         # HTML mocks с тестовыми PII (Level 2)
│   ├── timelines/
│   │   ├── static_figma/
│   │   ├── work_to_jobsearch/
│   │   └── productive_day/
│   ├── edge_cases/
│   └── real_web/          # Playwright скрины публичных сайтов (Level 3, опц.)
├── llm_responses/         # записанные VisionResult JSON для FakeLLMProvider
├── manifest.yaml          # метаданные (employee, project, task, timestamp)
└── README.md
```

## Как пересобрать

```bash
make generate-fixtures
```

или по отдельности:

```bash
uv run python tools/generate_placeholder_screenshots.py    # Level 1
uv run python tools/capture_html_mocks.py                  # Level 2
uv run python tools/capture_real_web.py                    # Level 3 (опц., медленно)
```

## Уровни синтеза

| Уровень | Источник | Скринов | Когда |
|---|---|---|---|
| 1. Placeholder | Pillow | ~50 | Каждый запуск тестов в CI |
| 2. HTML mocks | Playwright + HTML | ~15-20 | Каждый запуск (PII-тесты) |
| 3. Real web | Playwright + публичные сайты | ~15-20 | Только для live_llm тестов вручную |

## Запреты

- **PII** — только синтетические (`test@example.com`, `+7-000-000-0000`, `4111-1111-1111-1111`, `Иван Тестовый`/`John Doe`)
- НЕ использовать реальные данные клиентов/проектов/токенов
- НЕ скриншотить сайты, требующие логина под реальным аккаунтом
