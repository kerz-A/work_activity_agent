"""Тесты FilesystemPromptLoader."""

from pathlib import Path

import pytest

from work_activity_agent.domain.errors import PromptNotFoundError
from work_activity_agent.infrastructure.prompts.filesystem_loader import (
    FilesystemPromptLoader,
)


def _write_prompt(path: Path, frontmatter: str, body: str) -> None:
    content = f"---\n{frontmatter}---\n{body}"
    path.write_text(content, encoding="utf-8")


class TestFilesystemPromptLoader:
    def test_loads_valid_prompt(self, tmp_path: Path) -> None:
        _write_prompt(
            tmp_path / "vision.md",
            "name: vision\nversion: 1.0.0\nmodel_alias: vision_primary\n",
            "# System\nYou are an assistant.\n",
        )
        loader = FilesystemPromptLoader(tmp_path)
        result = loader.load("vision")
        assert result.name == "vision"
        assert result.version == "1.0.0"
        assert result.model_alias == "vision_primary"
        assert "You are an assistant" in result.content

    def test_loads_with_response_schema(self, tmp_path: Path) -> None:
        _write_prompt(
            tmp_path / "p.md",
            (
                "name: p\nversion: 1.0.0\nmodel_alias: text_primary\n"
                "response_schema: work_activity_agent.domain.models.vision.VisionResult\n"
            ),
            "body",
        )
        result = FilesystemPromptLoader(tmp_path).load("p")
        assert result.response_schema_ref == (
            "work_activity_agent.domain.models.vision.VisionResult"
        )

    def test_renders_jinja_variables(self, tmp_path: Path) -> None:
        _write_prompt(
            tmp_path / "p.md",
            "name: p\nversion: 1.0.0\nmodel_alias: text_primary\n",
            "Hello {{ name }}, you are {{ role }}",
        )
        result = FilesystemPromptLoader(tmp_path).load("p")
        rendered = result.render(name="Anna", role="dev")
        assert rendered == "Hello Anna, you are dev"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PromptNotFoundError):
            FilesystemPromptLoader(tmp_path).load("missing")

    def test_no_frontmatter_raises(self, tmp_path: Path) -> None:
        (tmp_path / "p.md").write_text("just content\n", encoding="utf-8")
        with pytest.raises(PromptNotFoundError):
            FilesystemPromptLoader(tmp_path).load("p")

    def test_loads_versioned_from_archive(self, tmp_path: Path) -> None:
        archive = tmp_path / "archive"
        archive.mkdir()
        _write_prompt(
            archive / "p.v0.9.0.md",
            "name: p\nversion: 0.9.0\nmodel_alias: text_primary\n",
            "old version",
        )
        result = FilesystemPromptLoader(tmp_path).load("p", version="0.9.0")
        assert result.version == "0.9.0"
