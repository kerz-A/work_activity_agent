"""Узел Collector: читает скриншоты из input_dir + manifest.yaml."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from work_activity_agent.application.state import AgentState, NodeError
from work_activity_agent.config.container import Deps
from work_activity_agent.domain.errors import ManifestParseError
from work_activity_agent.domain.models.screenshot import Screenshot, ScreenshotMetadata
from work_activity_agent.infrastructure.observability.logging import get_logger

# Конвенция имени файла: {employee}__{project}__{task}__{ISO timestamp}.png
# Используется как fallback если manifest.yaml не содержит записи для скриншота.
_FILENAME_RE = re.compile(
    r"^(?P<employee>[^_]+)__(?P<project>[^_]+)__(?P<task>[^_]+)__"
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})$"
)


def make_collector_node(deps: Deps) -> Callable[[AgentState], AgentState]:
    """Фабрика узла Collector. Возвращает функцию-узел, готовую к LangGraph."""

    log = get_logger("collector")

    def collector_node(state: AgentState) -> AgentState:
        log.info("collector.start", input_dir=str(state.input_dir), run_id=state.run_id)

        if not state.input_dir.exists():
            log.error("collector.input_missing", path=str(state.input_dir))
            return state.model_copy(
                update={
                    "errors": [
                        *state.errors,
                        NodeError(
                            node="collector",
                            screenshot_id=None,
                            message=f"input_dir does not exist: {state.input_dir}",
                        ),
                    ]
                }
            )

        manifest_metadata = _load_manifest_safe(state.input_dir, deps, state, log)

        screenshots: list[Screenshot] = []
        for path in deps.storage.list_screenshots(state.input_dir):
            screenshot = _build_screenshot(path, state.input_dir, manifest_metadata)
            if state.employee_filter and screenshot.metadata.employee_id != state.employee_filter:
                continue
            if state.date_filter and screenshot.captured_at.date() != state.date_filter:
                continue
            screenshots.append(screenshot)

        log.info("collector.done", screenshots_count=len(screenshots))
        return state.model_copy(update={"screenshots": screenshots})

    return collector_node


def _load_manifest_safe(
    input_dir: Path,
    deps: Deps,
    state: AgentState,
    log: object,
) -> dict[str, ScreenshotMetadata]:
    """Загрузить manifest.yaml — допустимо отсутствие, но не битый формат."""
    manifest_path = input_dir / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    try:
        return deps.manifest_loader.load(manifest_path)
    except ManifestParseError as e:
        # Логгируем, но не падаем — fallback на парсинг имени файла
        get_logger("collector").warning(
            "collector.manifest_parse_error", error=str(e), path=str(manifest_path)
        )
        return {}


def _build_screenshot(
    path: Path,
    input_root: Path,
    manifest: dict[str, ScreenshotMetadata],
) -> Screenshot:
    """Собрать Screenshot: метаданные из manifest.yaml > имя файла > пусто."""
    rel_path = path.relative_to(input_root).as_posix()
    metadata = manifest.get(rel_path, ScreenshotMetadata())

    captured_at = _extract_timestamp(path) or _file_mtime_utc(path)
    screenshot_id = path.stem

    return Screenshot(
        id=screenshot_id,
        path=path,
        captured_at=captured_at,
        metadata=metadata,
    )


def _extract_timestamp(path: Path) -> datetime | None:
    """Попробовать вытащить timestamp из имени файла по конвенции."""
    match = _FILENAME_RE.match(path.stem)
    if not match:
        return None
    ts_str = match.group("ts").replace("T", " ")
    parts = ts_str.split(" ")
    date_part = parts[0]
    time_part = parts[1].replace("-", ":")
    try:
        return datetime.fromisoformat(f"{date_part}T{time_part}").replace(tzinfo=UTC)
    except ValueError:
        return None


def _file_mtime_utc(path: Path) -> datetime:
    """Fallback: дата изменения файла как captured_at."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
