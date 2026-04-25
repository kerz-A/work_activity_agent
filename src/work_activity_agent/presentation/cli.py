"""CLI агента: typer-based.

Команды:
    run            — полный прогон с реальным LLM
    dry-run        — прогон с FakeLLM (без API)
    validate-prompts — golden тесты промптов
    version        — версия
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from work_activity_agent.application.graph import build_graph
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import build_dependencies
from work_activity_agent.config.settings import Settings

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


def _run_graph(deps: object, input_dir: Path) -> None:
    """Сборка графа и запуск."""
    from work_activity_agent.config.container import Deps

    assert isinstance(deps, Deps)

    graph = build_graph(deps)
    initial_state = AgentState(input_dir=input_dir)

    try:
        final_state_raw = asyncio.run(graph.ainvoke(initial_state))
    except Exception as e:
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
