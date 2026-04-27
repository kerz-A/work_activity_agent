# Runbook — deployment и эксплуатация

Документ описывает развёртывание `work-activity-agent` на новой машине, диагностику типовых проблем и операционные сценарии (resume, cleanup, профайлинг).

## Содержание

1. [Pre-flight checks](#pre-flight-checks)
2. [Профили развёртывания](#профили-развёртывания)
3. [Диагностика — `doctor` команда](#диагностика--doctor-команда)
4. [Типовые проблемы и решения](#типовые-проблемы-и-решения)
5. [Производительность и тюнинг](#производительность-и-тюнинг)
6. [Cleanup и переустановка](#cleanup-и-переустановка)

---

## Pre-flight checks

### Все профили

```bash
docker --version          # ожидается >= 24.0
docker compose version    # ожидается >= 2.20
docker info               # сервер должен быть запущен
```

### Для `local-llm` (полный Docker с локальной Ollama)

Дополнительно — GPU passthrough в Docker:

**Linux**:
```bash
# Установить NVIDIA Container Toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**Windows + WSL2**:
1. Docker Desktop → Settings → General → ✅ "Use the WSL 2 based engine"
2. Свежий NVIDIA driver (≥531) — Container Toolkit идёт автоматически с WSL2
3. Docker Desktop → Settings → Resources → WSL Integration → ✅ Enable for default distro

Проверка:
```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
# Должна быть видна ваша GPU
```

Если `nvidia-smi` внутри контейнера не сработал → используйте профиль `host-llm` или `cloud-llm`.

### Для `host-llm` (Ollama нативно)

```bash
# Установить Ollama: https://ollama.com/download

# Запустить (в отдельном терминале или как сервис)
ollama serve

# Скачать модель
ollama pull gemma3:4b

# Проверка
curl http://localhost:11434/api/tags
```

### Для `cloud-llm`

Получите API key:
- **Anthropic** (рекомендуется — Haiku 4.5 имеет vision): https://console.anthropic.com
- OpenAI: https://platform.openai.com/api-keys
- OpenRouter (есть бесплатные модели): https://openrouter.ai/keys

---

## Профили развёртывания

### Сравнительная таблица

| Параметр | `local-llm` | `host-llm` | `cloud-llm` |
|---|:---:|:---:|:---:|
| Полнота Docker-изоляции | ✅ полная | ⚠️ Ollama на хосте | ✅ полная |
| Зависимости хоста | Docker + GPU | Docker + Ollama | только Docker |
| GPU обязателен | Да (≥6 GB VRAM) | Желательно | Не нужен |
| Стоимость прогона | $0 | $0 | ~$0.5-1 |
| Время на 68 скринов | ~15-25 мин | ~15-20 мин | ~5-10 мин |
| Точность классификации | ~75% (Gemma 4B) | ~75% (Gemma 4B) | ~90%+ (Claude Haiku) |

### Профиль `local-llm` (рекомендуется для on-premise)

Архитектура: 2 контейнера (`agent` + `ollama`), оба в одной Docker-сети.

```
┌────────────────────────────────────────────────────┐
│ Docker network                                     │
│                                                    │
│  ┌────────────┐  http://ollama:11434  ┌─────────┐ │
│  │   agent    │ ─────────────────────→│ ollama  │ │
│  │ (Python)   │                       │ (GPU)   │ │
│  └────────────┘                       └─────────┘ │
│       ↑                                            │
│       │ volume                                     │
└───────┼────────────────────────────────────────────┘
        │
   ┌────┴─────┐
   │ host fs  │
   │ data/    │ ← input
   │ reports/ │ ← output
   └──────────┘
```

`.env`:
```
LLM_PROFILE=local
LLM_OLLAMA_BASE_URL=http://ollama:11434
LLM_PRIVACY_STRICT=true
LLM_MAX_CONCURRENT_VISION=2
LLM_REQUEST_TIMEOUT_S=180
LLM_SOFT_BUDGET_USD=0
```

Запуск:
```bash
docker build -t work-activity-agent:latest .
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local-llm up -d ollama
docker compose exec ollama ollama pull gemma3:4b
docker compose --profile local-llm run --rm agent doctor

docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

### Профиль `host-llm` (fallback при проблемах с GPU passthrough)

Архитектура: только агент в Docker, Ollama нативно.

```
┌─────────────────┐
│  Docker         │
│  ┌───────────┐  │
│  │  agent    │  │
│  └─────┬─────┘  │
└────────┼────────┘
         │ host.docker.internal:11434
┌────────┴────────┐
│  Host           │
│  ┌───────────┐  │
│  │  ollama   │  │
│  │  serve    │  │
│  └───────────┘  │
└─────────────────┘
```

`.env`:
```
LLM_PROFILE=local
LLM_OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_PRIVACY_STRICT=true
LLM_MAX_CONCURRENT_VISION=2
```

Запуск:
```bash
# В одном терминале
ollama serve

# В другом
ollama pull gemma3:4b
docker build -t work-activity-agent:latest .

docker compose --profile host-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

### Профиль `cloud-llm` (точность + скорость)

`.env`:
```
LLM_PROFILE=cloud
LLM_ANTHROPIC_API_KEY=sk-ant-...
LLM_PRIVACY_STRICT=true
LLM_SOFT_BUDGET_USD=2.0
LLM_MAX_CONCURRENT_VISION=4
LLM_REQUEST_TIMEOUT_S=120
```

Запуск:
```bash
docker build -t work-activity-agent:latest .
docker compose --profile cloud-llm run --rm \
  -v "$(pwd)/data:/app/data" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

---

## Диагностика — `doctor` команда

```bash
docker compose --profile local-llm run --rm agent doctor
```

Выводит таблицу `[OK]` / `[WARN]` / `[FAIL]` по 6 проверкам (по 7-ой подсекции в local-профиле — отдельные models/risk configs):

| # | Проверка | Severity | Что значит FAIL |
|:-:|---|:-:|---|
| 1 | Python ≥3.12 | FAIL | Образ собран не на 3.12 — пересоберите |
| 2 | Tesseract найден | FAIL (strict) / WARN (lax) | Образ старый или native без Tesseract — поставить пакет или `LLM_PRIVACY_STRICT=false` |
| 3 | LLM доступен (Ollama для local / API key для cloud) | FAIL | Сервис не поднят / `LLM_OLLAMA_BASE_URL` указывает в неверное место / нет `LLM_*_API_KEY` |
| 4 | presidio-image-redactor импортируется | FAIL (strict) / WARN (lax) | Не хватает `libgl1`/`libglib2.0-0` (для opencv) |
| 5 | spaCy en_core_web_sm загружена | FAIL (strict) / WARN (lax) | Модель не скачана при сборке/инсталле |
| 6 | `configs/models.{profile}.yaml` найден | FAIL | Файл не скопирован в образ или путь переопределён через `LLM_MODELS_CONFIG_PATH` неверно |
| 7 | `configs/default.yaml` найден | FAIL | Файл не скопирован в образ |

При любом FAIL exit code = 1 — `docker compose run` завершится с кодом ≠ 0. Используйте в CI/CD как gate.

Severity-логика: `FAIL` поднимается до `WARN` при `LLM_PRIVACY_STRICT=false` для проверок 2/4/5 — на них pipeline может работать без нужного компонента (с риском утечки PII в Vision).

---

## Типовые проблемы и решения

### Проблема: `Cannot connect to host localhost:11434`

**Причина**: Агент в Docker контейнере — `localhost` это сам контейнер, а не хост.

**Решение**: проверьте `.env`:
- Профиль `local-llm`: `LLM_OLLAMA_BASE_URL=http://ollama:11434`
- Профиль `host-llm`: `LLM_OLLAMA_BASE_URL=http://host.docker.internal:11434`

### Проблема: Vision-запросы виснут на 250s, ошибка `network_timeout`

**Причина**: модель медленно отвечает. Возможные причины:
1. GPU не используется (даже если `nvidia-smi` показывает GPU)
2. Vision-запросы идут на `/api/chat` endpoint (медленный для multimodal)
3. Image preprocessing на CPU из-за нехватки VRAM

**Решение**:
1. `docker compose exec ollama ollama ps` — колонка PROCESSOR должна быть `100% GPU` (или хотя бы split). Если `100% CPU` — VRAM нехватка или GPU passthrough сломан.
2. В `configs/models.local.yaml` префикс должен быть `ollama/` (= `/api/generate`), не `ollama_chat/` (= `/api/chat` — медленно).
3. Если VRAM <6 GB или используется большая часть — переключитесь на `host-llm` или `cloud-llm`.

### Проблема: `image: unknown format` от Ollama

**Причина**: PIL после Presidio возвращает RGBA или indexed PNG, Ollama vision encoder принимает только RGB.

**Решение**: уже исправлено — `presidio_image_redactor.py` конвертирует в RGB перед сохранением.

### Проблема: `Read-only file system: '/app/fixtures/.../foo.redacted.png'`

**Причина**: Pipeline пишет редактированные PNG рядом с оригиналом, но `fixtures/` смонтирован как `:ro`.

**Решение**: уже исправлено — redacted-файлы пишутся в `settings.checkpoint_dir / redacted/`.

### Проблема: `OllamaException - Cannot connect to host localhost:11434`

**Причина** (для контейнера агента): `LLM_OLLAMA_BASE_URL` не передался в контейнер.

**Решение**: явно через `-e`:
```bash
docker compose --profile host-llm run --rm \
  -e LLM_OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  agent run ...
```

### Проблема: Все скрины с одинаковыми timestamps

**Причина**: `captured_at` не указан в `manifest.yaml` — collector использует mtime файла.

**Решение**: укажите `captured_at` (ISO-8601 с timezone) в каждой записи manifest.

### Проблема: `relevances` все `UNCLEAR`, нет risk_flags

**Причина**: `tracked_task_title` не указан в manifest — Relevance node не вызывает LLM (skip без задачи).

**Решение**: добавьте `tracked_task_title` к каждой записи в manifest.

### Проблема: `BUDGET EXCEEDED` на cloud

**Причина**: `LLM_SOFT_BUDGET_USD` достигнут.

**Решение**: либо увеличить (`LLM_SOFT_BUDGET_USD=5.0`), либо `LLM_SOFT_BUDGET_USD=0` (отключить), либо переключиться на `LLM_PROFILE=local`.

### Проблема: `port 11434 already in use`

**Причина**: native Ollama держит порт; Docker Ollama не может стартовать.

**Решение**:
- Если хотите `local-llm`: остановить native — `Stop-Process -Name ollama -Force` (Win) / `pkill ollama` (Linux)
- Если хотите `host-llm`: оставить native, использовать профиль host-llm

---

## Производительность и тюнинг

### Время на этап (на 68 скринах, профиль `local-llm` с GPU GTX 1660 6 GB)

| Этап | Время | Ограничение |
|---|---|---|
| Collector | <1 сек | I/O чтение |
| ImageRedaction | ~5 мин | Tesseract OCR на CPU |
| Vision | ~10-15 мин | Gemma 3 4B на GPU |
| Classifier | ~5-7 мин | Текстовая Gemma на GPU |
| Relevance | ~3-5 мин | Текстовая Gemma на GPU |
| Timeline + Scoring + Reports | <1 сек | Чистая математика |
| **Итого** | **~25-30 мин** | |

### Параметры тюнинга

`.env`:
- **`LLM_MAX_CONCURRENT_VISION`** (default 2): параллельность Vision. На 6 GB VRAM = 1-2; на ≥8 GB можно 4. Cloud — 4-8.
- **`LLM_REQUEST_TIMEOUT_S`** (default 180): hard timeout. Поднять если cold-start модели долгий (~3-5 мин на первый запрос).
- **`LLM_SOFT_BUDGET_USD`** (default 5.0): для cloud. Установить 0 чтобы отключить.

`configs/default.yaml`:
- **`classifier.max_concurrent`** (2): параллельность Classifier. Текстовый — можно 4-6.
- **`relevance.max_concurrent`** (2): параллельность Relevance.

### Если в Docker GPU split mode (`45%/55% CPU/GPU`)

Это значит модель не помещается полностью в VRAM. Что делать:
1. **Освободить VRAM** — закрыть приложения с GPU использованием (Firefox, Discord, Chrome). `nvidia-smi` покажет кто занимает.
2. **Увеличить таймаут** — `LLM_REQUEST_TIMEOUT_S=300`.
3. **Перейти на меньшую модель**:
   ```bash
   docker compose exec ollama ollama pull moondream:1.8b
   ```
   В `configs/models.local.yaml`: `vision_primary: ollama/moondream:1.8b`. Минус — точность хуже Gemma.

---

## Cleanup и переустановка

### Удалить артефакты прогона (но сохранить модели)

```bash
# Linux/Mac/Git Bash
rm -rf demo_output/* .checkpoints/* data/reports/* run.log

# Windows PowerShell
Remove-Item -Recurse -Force demo_output\*, .checkpoints\*, data\reports\*, run.log -ErrorAction SilentlyContinue
```

### Полная переустановка Docker (любой профиль)

```bash
# Стоп всех контейнеров и volumes (Ollama-модели в local-llm придётся pull заново)
docker compose --profile local-llm down -v
docker compose --profile host-llm down -v
docker compose --profile cloud-llm down -v

# Удалить образы
docker rmi -f work-activity-agent:latest
docker rmi -f $(docker images "ollama/ollama" -q)        # Linux/Mac
# Windows PowerShell:
# docker images "ollama/ollama" -q | ForEach-Object { docker rmi -f $_ }

# Очистить build cache (обязательно для clean rebuild)
docker builder prune -af

# Пересобрать с нуля
docker build --no-cache -t work-activity-agent:latest .
```

### Native: удалить .venv и кеши

```bash
# Linux/Mac
rm -rf .venv __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov

# Windows PowerShell
Remove-Item -Recurse -Force .venv, __pycache__, .pytest_cache, .mypy_cache, .ruff_cache, htmlcov -ErrorAction SilentlyContinue
```

### Сброс настроек

```bash
# Linux/Mac
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env -Force
```

---

## CI/CD интеграция

### GitHub Actions (пример)

```yaml
- name: Build agent image
  run: docker build -t work-activity-agent:${{ github.sha }} .

- name: Run doctor (smoke test)
  run: docker run --rm work-activity-agent:${{ github.sha }} doctor
  env:
    LLM_PROFILE: cloud
    LLM_ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

- name: Run pipeline on test fixtures
  run: |
    docker compose --profile cloud-llm run --rm \
      -v "${{ github.workspace }}/fixtures:/app/fixtures:ro" \
      -v "${{ github.workspace }}/output:/app/output" \
      agent run --input /app/fixtures/screenshots --output /app/output
```

### Регулярный прогон по cron

```yaml
- cron: "0 18 * * 1-5"   # каждый рабочий день в 21:00 МСК
```

В runtime — монтировать сегодняшнюю директорию скринов:
```bash
TODAY=$(date +%Y-%m-%d)
docker compose --profile cloud-llm run --rm \
  -v "/data/screenshots/$TODAY:/app/data/screenshots:ro" \
  -v "/data/reports:/app/data/reports" \
  agent run --input /app/data/screenshots --output /app/data/reports
```

---

## Поддержка

- Issues: https://github.com/kerz-A/work_activity_agent/issues
- См. также: [README.md](../README.md), [docs/architecture.md](architecture.md), [docs/manifest.md](manifest.md)
