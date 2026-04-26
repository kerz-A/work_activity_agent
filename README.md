# work-activity-agent

AI агент анализа скриншотов из таск-трекера. Оцифровывает скриншоты сотрудников, классифицирует активность, считает risk score + work activity score, формирует отчёт менеджеру.

> **Принцип**: агент фиксирует только наблюдаемые факты с уровнем уверенности. Не выносит дисциплинарных решений и не делает выводов о намерениях. Все спорные эпизоды отдаются на ручную проверку.

## Status

🚧 В разработке. Этап: **0 — git init и базовый скелет**.

См. [план реализации](docs/) и [техническое задание](docs/tech_task.md).

## Архитектура

```
Collector → ImageRedaction → Vision → Classifier → Relevance → Timeline → Scoring → Reports
```

- **Pipeline**: LangGraph с checkpointing на SQLite
- **Vision**: LiteLLM (абстракция над Claude/GPT)
- **Privacy**: Presidio Image Redactor закрашивает PII на изображении ДО Vision
- **Scoring**: Risk Score (§5 ТЗ) + Work Activity Score (§14 ТЗ)
- **Архитектура**: Hexagonal — `domain/` без внешних зависимостей, `infrastructure/` за `Protocol`-портами

Подробнее: [docs/architecture.md](docs/architecture.md)

## Quick start

### Требования
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) для управления зависимостями
- Tesseract OCR (для Presidio Image Redactor)

### Установка

```bash
# Установить зависимости
make install

# Скопировать конфиг и заполнить API ключи
cp .env.example .env
# отредактируй .env: добавь LLM_GROQ_API_KEY (бесплатно: https://console.groq.com/keys)

# Установить pre-commit hooks
make pre-commit
```

### LLM провайдер

По умолчанию используется **OpenRouter** — облачный агрегатор open-source моделей с бесплатным free tier:
- **Vision**: `openrouter/meta-llama/llama-3.2-11b-vision-instruct:free`
- **Text**: `openrouter/meta-llama/llama-3.3-70b-instruct:free`

Получить API key: [openrouter.ai/keys](https://openrouter.ai/keys) (бесплатно, OAuth через Google/GitHub).

Сменить провайдера на Groq / Anthropic / OpenAI / Ollama локально — отредактируй [configs/models.yaml](configs/models.yaml) (alias → имя модели). Код не трогается.

### Запуск

```bash
# Прогон на тестовых фикстурах (без реального LLM)
make dry-run

# Прогон на тестовых фикстурах (с реальным LLM)
make demo

# Прогон на своих данных
make run
```

## Разработка

```bash
make lint              # ruff check
make format            # ruff format (автоформатирование)
make type              # mypy --strict
make test              # pytest (unit + integration)
make test-live-llm     # тесты с реальным LLM (требует API ключи)
make coverage          # отчёт coverage в htmlcov/
```

## Тестовые данные

Фикстуры синтезируются автоматически:

```bash
make generate-fixtures
```

Подробнее: [fixtures/README.md](fixtures/README.md)

## Документация

- [docs/architecture.md](docs/architecture.md) — архитектура
- [docs/prompts.md](docs/prompts.md) — работа с промптами
- [docs/runbook.md](docs/runbook.md) — дебаг упавших прогонов
- [docs/adr/](docs/adr/) — Architecture Decision Records
- [docs/tech_task.md](docs/tech_task.md) — техническое задание

## License

Лицензия не определена. Все права защищены автором.
