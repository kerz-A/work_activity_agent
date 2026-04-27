# syntax=docker/dockerfile:1.7

# =============================================================================
# Stage 1: builder — uv + Python deps
# =============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv для воспроизводимой установки
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Сначала только манифесты — для лучшего кеширования слоёв
COPY pyproject.toml uv.lock ./

# Установка зависимостей в .venv (без dev)
RUN uv sync --frozen --no-dev --no-install-project

# Теперь исходники проекта и установка самого пакета
COPY src/ src/
COPY README.md ./
RUN uv sync --frozen --no-dev

# spaCy NLP модель для Presidio Analyzer (без неё AnalyzerEngine падает на init →
# image_redaction поднимает RedactionError → privacy_strict отбрасывает все скрины).
# Используем `uv pip install` с прямым wheel URL — потому что в venv созданном через
# `uv sync` нет `pip`, а spacy.cli.download() требует pip/uv.
# Версия модели должна быть совместима с spacy>=3.8 (см. uv.lock).
RUN uv pip install --python /app/.venv/bin/python \
    "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"


# =============================================================================
# Stage 2: runtime — slim + Tesseract + наш пакет из builder
# =============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Системные зависимости:
#   - tesseract-ocr (+ языки) — для Presidio Image Redactor
#   - libgl1, libglib2.0-0 — нужны opencv-python (transitive от presidio-image-redactor)
#     На python:3.12-slim их нет; без них `import presidio_image_redactor` падает с
#     "libGL.so.1: cannot open shared object file"
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Виртуальное окружение из builder-стадии
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Конфиги и промпты копируются явно (не внутри пакета — собираются как relative paths)
COPY configs/ /app/configs/

# Дефолтные пути работы (можно переопределить через env / volume)
ENV INPUT_DIR=/app/data/screenshots \
    OUTPUT_DIR=/app/data/reports \
    CHECKPOINT_DIR=/app/.checkpoints

RUN mkdir -p /app/data/screenshots /app/data/reports /app/.checkpoints

# Fail-fast smoke-test: проверяем что критичные модули импортятся в собранном образе.
# Если на этом шаге fail — образ не соберётся, и пользователь увидит ошибку при build,
# а не на runtime когда уже всё отбросится.
RUN /app/.venv/bin/python -c "\
import presidio_image_redactor; \
from presidio_image_redactor import ImageRedactorEngine; \
import spacy; spacy.load('en_core_web_sm'); \
import pytesseract; pytesseract.get_tesseract_version(); \
print('Presidio + spaCy + Tesseract: OK')"

ENTRYPOINT ["work-activity-agent"]
CMD ["doctor"]
