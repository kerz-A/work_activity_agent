"""CLI заглушка. Полная реализация — в следующих коммитах."""

import typer

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
