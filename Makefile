.PHONY: help install sync lint format type test test-unit test-integration test-live-llm test-all coverage clean demo run dry-run validate-prompts generate-fixtures pre-commit

PYTHON := uv run python
PYTEST := uv run pytest
RUFF := uv run ruff
MYPY := uv run mypy

help:
	@echo "Доступные команды:"
	@echo "  make install            — установить зависимости (uv sync --all-extras --dev)"
	@echo "  make sync               — синхронизировать lock-файл"
	@echo "  make lint               — ruff check + ruff format --check"
	@echo "  make format             — ruff format (автоформатирование)"
	@echo "  make type               — mypy --strict"
	@echo "  make test               — все тесты кроме live_llm"
	@echo "  make test-unit          — только unit тесты"
	@echo "  make test-integration   — только integration тесты"
	@echo "  make test-live-llm      — live LLM тесты (требует API ключи)"
	@echo "  make test-all           — все включая live_llm"
	@echo "  make coverage           — отчёт coverage в htmlcov/"
	@echo "  make clean              — удалить кеши и артефакты"
	@echo "  make demo               — прогнать агента на fixtures/"
	@echo "  make run                — прогнать агента на data/screenshots/"
	@echo "  make dry-run            — прогон с FakeLLM (без API)"
	@echo "  make validate-prompts   — golden тесты промптов"
	@echo "  make generate-fixtures  — пересобрать тестовые скриншоты"
	@echo "  make pre-commit         — установить pre-commit hooks"

install:
	uv sync --all-extras --dev

sync:
	uv lock

lint:
	$(RUFF) check src tests tools
	$(RUFF) format --check src tests tools

format:
	$(RUFF) check --fix src tests tools
	$(RUFF) format src tests tools

type:
	$(MYPY) src

test:
	$(PYTEST)

test-unit:
	$(PYTEST) tests/unit -v

test-integration:
	$(PYTEST) tests/integration -v

test-live-llm:
	$(PYTEST) -m live_llm -v

test-all:
	$(PYTEST) -m "" -v

coverage:
	$(PYTEST) --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage* dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

demo:
	$(PYTHON) -m work_activity_agent run --input ./fixtures/screenshots --output ./demo_output

run:
	$(PYTHON) -m work_activity_agent run --input ./data/screenshots --output ./data/reports

dry-run:
	$(PYTHON) -m work_activity_agent dry-run --input ./fixtures/screenshots

validate-prompts:
	$(PYTEST) tests/golden -v

generate-fixtures:
	$(PYTHON) tools/generate_placeholder_screenshots.py
	$(PYTHON) tools/capture_html_mocks.py

pre-commit:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
