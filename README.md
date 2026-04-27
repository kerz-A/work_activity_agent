# work-activity-agent

AI-агент анализа скриншотов из таск-трекера. Оцифровывает скриншоты сотрудников, классифицирует активность по 11 категориям, сравнивает с задачами в трекере, считает Risk Score (§5 ТЗ) + Work Activity Score (§14 ТЗ), формирует отчёты менеджеру.

> **Принцип**: агент фиксирует только наблюдаемые факты с уровнем уверенности. Не выносит дисциплинарных решений и не делает выводов о намерениях. Все спорные эпизоды отдаются на ручную проверку.

## Pipeline

```
Collector → ImageRedaction → Vision → Classifier → Relevance → Timeline → Scoring → Reports
```

- **LangGraph** оркестрация, immutable state
- **LiteLLM** под Vision/Classifier (Ollama локально или Anthropic/OpenAI/OpenRouter в cloud)
- **Presidio Image Redactor** закрашивает PII на изображении **до** Vision (privacy by default)
- **Hexagonal architecture** — `domain/` без внешних зависимостей, `infrastructure/` за Protocol-портами

Подробнее: [docs/architecture.md](docs/architecture.md)

---

## Quickstart

Три профиля развёртывания. Выберите подходящий:

| Профиль | Когда использовать | Изоляция | Скорость | Стоимость |
|---|---|:---:|:---:|:---:|
| **`local-llm`** | Полная Docker-изоляция; есть NVIDIA GPU + WSL2 (Windows) или Linux | Полная | ~15-25 мин на 68 скринов | $0 |
| **`host-llm`** | Хочешь Docker-изоляцию агента, Ollama уже стоит нативно (или есть проблемы с GPU passthrough) | Частичная | ~15-20 мин | $0 |
| **`cloud-llm`** | Серверы без GPU; нужна максимальная точность; готов платить | Полная | ~5-10 мин | ~$0.5-1 за 68 скринов |

### Pre-flight для всех профилей

```bash
# Проверить версии
docker --version          # >= 24.0
docker compose version    # >= 2.20

# Скопировать env template и отредактировать
cp .env.example .env
```

---

### Профиль 1 — `local-llm` (полная Docker изоляция, локальный GPU)

**Требования**: Docker Desktop с WSL2 backend (Windows) или Docker Engine (Linux), NVIDIA GPU + NVIDIA driver на хосте, NVIDIA Container Toolkit (для Linux/WSL2).

**Setup GPU passthrough** (если ещё нет):
- Linux: установите [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Windows: WSL2 + свежий NVIDIA driver (≥531) — Container Toolkit идёт автоматически

**Проверка GPU passthrough**:
```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
# Должна быть показана ваша GPU
```

**В `.env`**:
```
LLM_PROFILE=local
LLM_OLLAMA_BASE_URL=http://ollama:11434
LLM_PRIVACY_STRICT=true
LLM_SOFT_BUDGET_USD=0
LLM_MAX_CONCURRENT_VISION=2
LLM_REQUEST_TIMEOUT_S=180
```

**Запуск**:
```bash
# 1. Собрать образ агента (один раз)
docker build -t work-activity-agent:latest .

# 2. Поднять Ollama в Docker с GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local-llm up -d ollama

# 3. Скачать модель (один раз, ~3 минуты)
docker compose exec ollama ollama pull gemma3:4b

# 4. Проверка окружения
docker compose --profile local-llm run --rm agent doctor
# Должны быть все [OK]

# 5. Прогон pipeline на ваших скринах
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

GPU split mode (`45%/55% CPU/GPU`) на 6 GB VRAM нормален — pipeline всё равно отрабатывает за 15-25 минут. Если VRAM ≥8 GB — будет полностью на GPU и в 2× быстрее.

---

### Профиль 2 — `host-llm` (Ollama нативно + agent в Docker)

**Когда выбирать**: GPU passthrough в Docker не работает или WSL2 даёт overhead, но нативная Ollama уже установлена и работает.

**Требования**: [Ollama](https://ollama.com/download) установлена нативно на хосте.

**В `.env`**:
```
LLM_PROFILE=local
LLM_OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_PRIVACY_STRICT=true
LLM_MAX_CONCURRENT_VISION=2
```

**Запуск**:
```bash
# 1. Запустить Ollama нативно (в отдельном терминале)
ollama serve

# В другом терминале:
ollama pull gemma3:4b

# 2. Собрать образ агента
docker build -t work-activity-agent:latest .

# 3. Прогон через профиль host-llm (без sidecar Ollama)
docker compose --profile host-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

---

### Профиль 3 — `cloud-llm` (Anthropic / OpenAI / OpenRouter)

**Когда выбирать**: серверы без GPU, нужна максимальная точность Vision (Claude Haiku 4.5 значительно точнее Gemma 3 4B).

**В `.env`**:
```
LLM_PROFILE=cloud
LLM_ANTHROPIC_API_KEY=sk-ant-...        # ИЛИ LLM_OPENAI_API_KEY / LLM_OPENROUTER_API_KEY
LLM_PRIVACY_STRICT=true
LLM_SOFT_BUDGET_USD=2.0                 # стоп при превышении $2
LLM_MAX_CONCURRENT_VISION=4
LLM_REQUEST_TIMEOUT_S=120
```

**Запуск**:
```bash
docker build -t work-activity-agent:latest .

docker compose --profile cloud-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

Стоимость: ~$0.5-1 за 68 скринов через Anthropic Claude Haiku 4.5.

OpenRouter имеет бесплатные vision-модели — впишите в `configs/models.cloud.yaml`:
```yaml
vision_primary: openrouter/google/gemma-3-12b-it:free
text_primary: openrouter/google/gemma-3-12b-it:free
```

---

## Native запуск (без Docker)

Для разработки и быстрых итераций:

```bash
# Зависимости
make install                       # uv sync --all-extras --dev
cp .env.example .env

# Tesseract (для image redaction):
#   Linux:   apt install tesseract-ocr
#   Mac:     brew install tesseract
#   Windows: https://github.com/UB-Mannheim/tesseract/wiki

# spaCy NLP-модель (для Presidio Analyzer):
uv run python -m pip install \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Ollama локально (https://ollama.com), или cloud key в .env
ollama pull gemma3:4b

# Проверка окружения
work-activity-agent doctor

# Запуск
work-activity-agent run --input ./data/screenshots --output ./data/reports
```

---

## Формат входных данных

Манифест `manifest.yaml` рядом со скриншотами:

```yaml
version: 1
screenshots:
  - file: shot_001.png
    employee_id: developer_1
    project_id: client_crm
    task_id: TASK-123
    tracked_task_title: "Fix payment retry bug"
    captured_at: '2026-04-22T09:00:00+00:00'
    tracked_minutes: 10
    app_hint: "VS Code"
```

Полная спецификация: [docs/manifest.md](docs/manifest.md). Минимальный пример: [examples/sample_input/](examples/sample_input/).

## Что получите на выходе

См. [examples/sample_output/](examples/sample_output/):
- `employee_<id>_<date>.md/.json` — дневной отчёт по сотруднику
- `project_<id>_<period>.md/.json` — проектный отчёт
- `screenshots_table.md/.json` — сводная таблица всех скринов (§15 ТЗ)

---

## Команды CLI

| Команда | Назначение |
|---|---|
| `work-activity-agent doctor` | Проверка окружения (Tesseract / Ollama / Presidio / spaCy / API keys / configs) |
| `work-activity-agent run --input <dir>` | Полный прогон pipeline на реальном LLM |
| `work-activity-agent dry-run --input <dir>` | Прогон с FakeLLM (без API, для smoke-теста) |
| `work-activity-agent validate-prompts` | Golden-тесты промптов |
| `work-activity-agent version` | Версия |

## Troubleshooting

| Проблема | Что делать |
|---|---|
| `Ollama не отвечает на http://ollama:11434` | Поднимите Ollama: `docker compose --profile local-llm up -d ollama` или используйте `host-llm` профиль |
| `Cannot connect to host localhost:11434` | Контейнер агента ходит в самого себя. Проверьте `LLM_OLLAMA_BASE_URL` в `.env` — должен быть `http://ollama:11434` (Docker) или `http://host.docker.internal:11434` (host-llm) |
| `Tesseract не найден` | Используйте Docker (Tesseract уже внутри). Native: установите по инструкциям выше или поставьте `LLM_PRIVACY_STRICT=false` (с риском утечки PII) |
| `presidio-image-redactor not installed` | Не хватает opencv libs. Используйте Docker (есть `libgl1` + `libglib2.0-0`). Native: `apt install libgl1 libglib2.0-0` |
| `spaCy en_core_web_sm не установлена` | См. native install выше — модель ставится из github wheel |
| Vision-таймауты на 250s+ в Docker | GPU passthrough не работает / WSL2 overhead. Проверьте `docker run --gpus all nvidia/cuda nvidia-smi`. Если не работает — используйте `host-llm` или `cloud-llm` |
| `image: unknown format` от Ollama | Уже исправлено — RGB конверсия + 1024px downscale в Presidio |
| Все скрины с datetime = время копирования | Заполните `captured_at` в `manifest.yaml` — без него используется mtime файла |
| `relevances` пустые | Заполните `tracked_task_title` в `manifest.yaml` — без него Relevance не работает |
| `BUDGET EXCEEDED` (cloud) | Увеличьте `LLM_SOFT_BUDGET_USD` или переключитесь на `LLM_PROFILE=local` |
| `address already in use` для порта 11434 | Другая Ollama уже запущена. Стопните native: `Stop-Process -Name ollama -Force` (PowerShell) или `pkill ollama` (Linux) |

В первую очередь — `work-activity-agent doctor`.

Подробный deployment guide и troubleshooting: [docs/runbook.md](docs/runbook.md).

---

## Разработка

```bash
make lint              # ruff check + format --check
make format            # ruff format
make type              # mypy --strict
make test              # pytest unit + integration
make coverage          # покрытие в htmlcov/
```

Тестовые данные: `make generate-fixtures` (Pillow + HTML mocks). Подробнее: [fixtures/README.md](fixtures/README.md).

## Документация

- [docs/architecture.md](docs/architecture.md) — архитектурные решения
- [docs/runbook.md](docs/runbook.md) — deployment guide и troubleshooting
- [docs/manifest.md](docs/manifest.md) — формат manifest.yaml
- [docs/prompts.md](docs/prompts.md) — работа с промптами
- [docs/adr/](docs/adr/) — Architecture Decision Records
- [docs/tech_task.md](docs/tech_task.md) — техническое задание

## License

[MIT](LICENSE)
