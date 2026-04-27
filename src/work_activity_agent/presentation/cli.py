"""CLI агента: typer-based.

Команды:
    doctor         — проверка окружения (Tesseract / Ollama / API keys / configs)
    run            — полный прогон с реальным LLM
    dry-run        — прогон с FakeLLM (без API)
    validate-prompts — golden тесты промптов
    version        — версия
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import typer

from work_activity_agent.application.graph import build_graph
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps, build_dependencies
from work_activity_agent.config.settings import Settings
from work_activity_agent.infrastructure.observability.logging import get_logger

_log = get_logger("cli")


def _ensure_utf8_console() -> None:
    """На Windows консоль по умолчанию cp1251 — `→`/«ё» в сообщениях падают
    с UnicodeEncodeError. Перенастраиваем stdout/stderr на utf-8 + replace,
    чтобы CLI не падал из-за кодировки. Идемпотентно."""
    import contextlib

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")


_ensure_utf8_console()

app = typer.Typer(
    name="work-activity-agent",
    help="AI агент анализа скриншотов из таск-трекера",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Показать версию."""
    from work_activity_agent import __version__

    typer.echo(f"work-activity-agent {__version__}")


@app.command()
def doctor() -> None:
    """Проверить окружение: Python, Tesseract, Ollama / API keys, configs.

    Возвращает exit=1 при FAIL.
    """
    settings = Settings()
    profile = settings.llm.profile
    privacy_strict = settings.llm.privacy_strict

    typer.echo("=" * 64)
    typer.echo(f"work-activity-agent doctor — profile={profile} strict={privacy_strict}")
    typer.echo("=" * 64)

    failures = 0
    failures += _check_python()
    failures += _check_tesseract(privacy_strict)
    failures += _check_llm(settings, profile)
    failures += _check_presidio(privacy_strict)
    failures += _check_spacy(privacy_strict)
    failures += _check_configs(settings, profile)

    typer.echo("=" * 64)
    if failures > 0:
        typer.echo(f"FAILED ({failures} проблем) — окружение не готово.")
        raise typer.Exit(code=1)
    typer.echo("OK — окружение готово к запуску.")


def _check_python() -> int:
    py_ver = sys.version_info
    if py_ver >= (3, 12):
        typer.echo(f"[OK]   Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
        return 0
    typer.echo(f"[FAIL] Python {py_ver.major}.{py_ver.minor} (требуется ≥3.12)")
    return 1


def _check_tesseract(privacy_strict: bool) -> int:
    tesseract = shutil.which("tesseract")
    if tesseract:
        typer.echo(f"[OK]   Tesseract: {tesseract}")
        return 0

    from work_activity_agent.infrastructure.redaction.presidio_image_redactor import (
        _autodetect_tesseract,
    )

    detected = _autodetect_tesseract()
    if detected:
        typer.echo(f"[OK]   Tesseract: {detected} (autodetected)")
        return 0
    if privacy_strict:
        typer.echo(
            "[FAIL] Tesseract не найден. privacy_strict=true → скриншоты будут "
            "отбрасываться при ошибке redaction.\n"
            "       Установка: apt install tesseract-ocr (Linux) / "
            "brew install tesseract (Mac) / https://github.com/UB-Mannheim/tesseract/wiki (Windows)"
        )
        return 1
    typer.echo("[WARN] Tesseract не найден. privacy_strict=false → оригинал PII попадёт в Vision.")
    return 0


def _check_llm(settings: Settings, profile: str) -> int:
    if profile == "local":
        return _check_ollama(settings.llm.ollama_base_url)
    return _check_cloud_keys(settings)


def _check_ollama(ollama_url: str) -> int:
    try:
        import httpx

        response = httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
        if response.status_code == 200:
            models = [m.get("name", "?") for m in response.json().get("models", [])]
            typer.echo(f"[OK]   Ollama at {ollama_url} (models: {', '.join(models) or '∅'})")
            return 0
        typer.echo(f"[FAIL] Ollama at {ollama_url} returned {response.status_code}")
        return 1
    except Exception as e:
        typer.echo(
            f"[FAIL] Ollama не отвечает на {ollama_url}: {type(e).__name__}\n"
            f"       Запустите `ollama serve` (нативно) или "
            f"`docker compose --profile local-llm up` (Docker).\n"
            f"       Скачать: https://ollama.com"
        )
        _log.debug("doctor.ollama_unreachable", url=ollama_url, error=str(e)[:200])
        return 1


def _check_cloud_keys(settings: Settings) -> int:
    any_key = any(
        getattr(settings.llm, attr) is not None
        for attr in (
            "anthropic_api_key",
            "openai_api_key",
            "openrouter_api_key",
            "groq_api_key",
        )
    )
    if any_key:
        typer.echo("[OK]   Хотя бы один LLM API key выставлен")
        return 0
    typer.echo(
        "[FAIL] Не выставлен ни один LLM_*_API_KEY для cloud-профиля.\n"
        "       Добавьте в .env: LLM_ANTHROPIC_API_KEY=... (или OPENAI / OPENROUTER / GROQ)"
    )
    return 1


def _check_presidio(privacy_strict: bool) -> int:
    try:
        from presidio_image_redactor import ImageRedactorEngine  # noqa: F401

        typer.echo("[OK]   presidio-image-redactor импортируется")
        return 0
    except ImportError as e:
        if privacy_strict:
            typer.echo(
                f"[FAIL] presidio-image-redactor не импортируется: {e}\n"
                "       Возможные причины: missing opencv libs (libgl1, libglib2.0-0), "
                "или пакет не установлен.\n"
                "       Docker: пересоберите образ с обновлённым Dockerfile.\n"
                "       Native: apt install libgl1 libglib2.0-0 && uv sync"
            )
            return 1
        typer.echo(f"[WARN] presidio-image-redactor не импортируется: {e}")
        return 0


def _check_spacy(privacy_strict: bool) -> int:
    try:
        import spacy

        spacy.load("en_core_web_sm")
        typer.echo("[OK]   spaCy en_core_web_sm загружена")
        return 0
    except OSError:
        if privacy_strict:
            typer.echo(
                "[FAIL] spaCy модель en_core_web_sm не установлена. Без неё Presidio Analyzer "
                "падает → privacy_strict=true отбросит все скрины.\n"
                "       Установка: python -m spacy download en_core_web_sm"
            )
            return 1
        typer.echo(
            "[WARN] spaCy en_core_web_sm не установлена. Presidio будет деградировать к fallback."
        )
        return 0
    except ImportError:
        typer.echo("[WARN] spacy не установлен в окружении")
        return 0


def _check_configs(settings: Settings, profile: str) -> int:
    failures = 0
    models_path = settings.llm.resolved_models_config_path
    if models_path.exists():
        typer.echo(f"[OK]   models config: {models_path}")
    else:
        typer.echo(
            f"[FAIL] models config не найден: {models_path}\n"
            f"       Должен быть configs/models.{profile}.yaml или укажите LLM_MODELS_CONFIG_PATH"
        )
        failures += 1

    risk_path = settings.risk.config_path
    if risk_path.exists():
        typer.echo(f"[OK]   risk config: {risk_path}")
    else:
        typer.echo(f"[FAIL] risk config не найден: {risk_path}")
        failures += 1
    return failures


@app.command()
def run(
    input_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--input",
        "-i",
        help="Директория со скриншотами",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("./data/reports"),
        "--output",
        "-o",
        help="Куда сохранить отчёты",
    ),
) -> None:
    """Запустить агента на реальных данных через LiteLLM (требует API ключи)."""
    settings = Settings()
    settings = settings.model_copy(update={"input_dir": input_dir, "output_dir": output_dir})
    deps = build_dependencies(settings, use_fake_llm=False, use_noop_redactor=False)
    _run_graph(deps, input_dir)


@app.command(name="dry-run")
def dry_run(
    input_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--input",
        "-i",
        help="Директория со скриншотами",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("./demo_output"),
        "--output",
        "-o",
        help="Куда сохранить отчёты",
    ),
) -> None:
    """Прогон с FakeLLM + Noop redactor — без API ключей."""
    settings = Settings()
    settings = settings.model_copy(update={"input_dir": input_dir, "output_dir": output_dir})
    deps = build_dependencies(settings, use_fake_llm=True, use_noop_redactor=True)

    # Регистрируем минимальные fallback-ответы для FakeLLM
    from work_activity_agent.domain.enums import ActivityType, RelevanceLevel
    from work_activity_agent.domain.models.classification import (
        ClassificationResult,
        RelevanceResult,
    )
    from work_activity_agent.domain.models.vision import VisionResult

    fake = deps.llm
    fake.set_default(  # type: ignore[attr-defined]
        VisionResult,
        {
            "screenshot_id": "default",
            "visible_application": "Unknown",
            "visible_site": None,
            "visible_page_type": None,
            "visible_text": [],
            "interpreted_activity": "Unknown activity (dry-run mode)",
            "extracted_metadata": {},
            "confidence": 0.5,
            "model_used": "fake/dry-run",
        },
    )
    fake.set_default(  # type: ignore[attr-defined]
        ClassificationResult,
        {
            "screenshot_id": "default",
            "activity_type": ActivityType.NEUTRAL_UNCLEAR.value,
            "category": "unknown",
            "evidence": ["dry-run mode, no real classification"],
            "confidence": 0.5,
        },
    )
    fake.set_default(  # type: ignore[attr-defined]
        RelevanceResult,
        {
            "screenshot_id": "default",
            "tracked_task": "unknown",
            "screenshot_activity": "unknown",
            "relevance": RelevanceLevel.UNCLEAR.value,
            "risk_flags": [],
            "confidence": 0.5,
            "note": "dry-run mode",
        },
    )

    _run_graph(deps, input_dir)


@app.command(name="validate-prompts")
def validate_prompts() -> None:
    """Запустить golden тесты промптов (структура frontmatter, рендеринг)."""
    typer.echo("Validating prompts in configs/prompts/...")
    prompts_dir = Path("configs/prompts")
    if not prompts_dir.exists():
        typer.echo(f"ERROR: {prompts_dir} does not exist", err=True)
        raise typer.Exit(code=1)

    from work_activity_agent.domain.errors import PromptNotFoundError
    from work_activity_agent.infrastructure.prompts.filesystem_loader import (
        FilesystemPromptLoader,
    )

    loader = FilesystemPromptLoader(prompts_dir)
    failed = 0
    for path in sorted(prompts_dir.glob("*.md")):
        name = path.stem
        try:
            template = loader.load(name)
            typer.echo(f"  OK {name} v{template.version}")
        except PromptNotFoundError as e:
            typer.echo(f"  FAIL {name}: {e}", err=True)
            failed += 1

    if failed > 0:
        typer.echo(f"\n{failed} prompts failed validation", err=True)
        raise typer.Exit(code=1)
    typer.echo("\nAll prompts valid.")


def _run_graph(deps: Deps, input_dir: Path) -> None:
    """Сборка графа и запуск."""
    if not isinstance(deps, Deps):
        raise TypeError(f"expected Deps, got {type(deps).__name__}")

    graph = build_graph(deps)
    initial_state = AgentState(input_dir=input_dir)

    from work_activity_agent.domain.errors import LLMBudgetExceededError

    try:
        final_state_raw = asyncio.run(graph.ainvoke(initial_state))
    except LLMBudgetExceededError as e:
        typer.echo(
            f"\n[BUDGET EXCEEDED] {e}\n"
            f"  Reports не сгенерированы. Увеличьте LLM_SOFT_BUDGET_USD "
            f"в .env или переключитесь на LLM_PROFILE=local.",
            err=True,
        )
        raise typer.Exit(code=3) from e
    except Exception as e:
        # Полный traceback идёт в structured лог; пользователю — короткое сообщение.
        _log.exception("cli.pipeline_failed", error_type=type(e).__name__)
        typer.echo(f"ERROR during pipeline: {type(e).__name__}: {e}", err=True)
        raise typer.Exit(code=2) from e

    final_state = AgentState.model_validate(final_state_raw)
    _print_summary(final_state, deps.settings.output_dir)


def _print_summary(state: AgentState, output_dir: Path) -> None:
    """Печать итогового summary в stdout."""
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("Pipeline finished")
    typer.echo("=" * 60)
    typer.echo(f"Run ID:               {state.run_id}")
    typer.echo(f"Screenshots analyzed: {len(state.screenshots)}")
    typer.echo(f"Vision results:       {len(state.vision_results)}")
    typer.echo(f"Classifications:      {len(state.classifications)}")
    typer.echo(f"Relevances:           {len(state.relevances)}")
    typer.echo(f"Timeline patterns:    {len(state.timeline_patterns)}")
    typer.echo(f"Employee reports:     {len(state.employee_reports)}")
    typer.echo(f"Project reports:      {len(state.project_reports)}")
    typer.echo(f"Errors (non-fatal):   {len(state.errors)}")

    if state.employee_reports:
        typer.echo("")
        typer.echo("Employee reports:")
        for r in state.employee_reports:
            review_count = sum(1 for f in r.risk_flags if f.requires_human_review)
            typer.echo(
                f"  - {r.employee_id} ({r.date.isoformat()}): "
                f"risk={r.risk_score.score} ({r.risk_score.level.value}), "
                f"work={r.work_activity_score.score} ({r.work_activity_score.level.value}), "
                f"review_required={review_count}"
            )

    if state.errors:
        typer.echo("")
        typer.echo("Non-fatal errors:")
        for err in state.errors[:5]:
            typer.echo(f"  - [{err.node}] {err.screenshot_id}: {err.message[:100]}")
        if len(state.errors) > 5:
            typer.echo(f"  ... and {len(state.errors) - 5} more")

    typer.echo("")
    typer.echo(f"Output saved to: {output_dir}")


if __name__ == "__main__":
    app()
