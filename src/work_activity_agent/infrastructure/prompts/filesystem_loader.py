"""FilesystemPromptLoader — загружает промпты из .md файлов с YAML frontmatter.

Формат файла:

    ---
    name: vision_describe
    version: 1.0.0
    model_alias: vision_primary
    response_schema: work_activity_agent.domain.models.vision.VisionResult
    description: Оцифровка скриншота
    ---

    # System

    Ты — Work Activity Screenshot Analysis Agent. ...

    # User

    Проанализируй скриншот {{ screenshot_id }}. ...
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from work_activity_agent.domain.errors import PromptNotFoundError
from work_activity_agent.domain.ports.prompt_loader import PromptTemplate

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)


class FilesystemPromptLoader:
    """Загружает промпты из директории `prompts_dir`."""

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir

    def load(self, name: str, *, version: str | None = None) -> PromptTemplate:
        """Загрузить промпт по имени.

        Если version указана — ищем `{name}.v{version}.md` в archive/, иначе `{name}.md`.
        """
        if version is not None:
            path = self._prompts_dir / "archive" / f"{name}.v{version}.md"
        else:
            path = self._prompts_dir / f"{name}.md"

        if not path.exists():
            raise PromptNotFoundError(name, version=version)

        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if not match:
            raise PromptNotFoundError(
                name,
                version=version,
            )

        frontmatter_yaml = match.group("frontmatter")
        body = match.group("body").strip()

        try:
            metadata = yaml.safe_load(frontmatter_yaml) or {}
        except yaml.YAMLError as e:
            raise PromptNotFoundError(name, version=version) from e

        if not isinstance(metadata, dict):
            raise PromptNotFoundError(name, version=version)

        return PromptTemplate(
            name=str(metadata.get("name", name)),
            version=str(metadata.get("version", "0.1.0")),
            model_alias=str(metadata.get("model_alias", "text_primary")),
            response_schema_ref=metadata.get("response_schema"),
            description=metadata.get("description"),
            content=body,
        )
