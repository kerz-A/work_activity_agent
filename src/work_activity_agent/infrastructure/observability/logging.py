"""structlog setup. JSON-логи в production, читабельные в dev."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from work_activity_agent.config.settings import ObservabilitySettings


def configure_logging(settings: ObservabilitySettings) -> None:
    """Настроить structlog глобально.

    Вызывается один раз на старте приложения (CLI / entrypoint).
    Идемпотентна.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.typing.Processor
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(_log_level_to_int(settings.log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Получить bound logger с начальным контекстом.

    Используй в каждом узле:

        log = get_logger("vision", run_id=state.run_id)
        log.info("vision.start", screenshots_count=len(state.screenshots))
    """
    logger = structlog.get_logger(name)
    if initial_context:
        return logger.bind(**initial_context)  # type: ignore[no-any-return]
    return logger  # type: ignore[no-any-return]


def _log_level_to_int(level: str) -> int:
    """Перевести строковый уровень в int для filtering bound logger."""
    value = getattr(logging, level)
    if not isinstance(value, int):
        raise ValueError(f"unknown log level: {level}")
    return value
