"""Тесты YamlManifestLoader."""

from pathlib import Path

import pytest

from work_activity_agent.domain.errors import ManifestParseError
from work_activity_agent.infrastructure.storage.manifest_yaml import YamlManifestLoader


@pytest.fixture
def loader() -> YamlManifestLoader:
    return YamlManifestLoader()


class TestYamlManifestLoaderHappyPath:
    def test_loads_full_entry(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            """
version: 1
screenshots:
  - file: productive/dev1_vscode_001.png
    employee_id: developer_1
    project_id: client_crm
    task_id: TASK-123
    tracked_task_title: "Fix payment retry bug"
    tracked_minutes: 10
    app_hint: "VS Code"
""",
            encoding="utf-8",
        )
        result = loader.load(manifest)
        assert "productive/dev1_vscode_001.png" in result
        meta = result["productive/dev1_vscode_001.png"]
        assert meta.employee_id == "developer_1"
        assert meta.project_id == "client_crm"
        assert meta.task_id == "TASK-123"
        assert meta.tracked_task_title == "Fix payment retry bug"
        assert meta.tracked_minutes == 10
        assert meta.app_hint == "VS Code"

    def test_loads_minimal_entry(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            """
version: 1
screenshots:
  - file: a.png
""",
            encoding="utf-8",
        )
        result = loader.load(manifest)
        assert "a.png" in result
        assert result["a.png"].employee_id is None

    def test_normalizes_windows_path_separators(
        self, tmp_path: Path, loader: YamlManifestLoader
    ) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            """
version: 1
screenshots:
  - file: productive\\dev1.png
    employee_id: dev_1
""",
            encoding="utf-8",
        )
        result = loader.load(manifest)
        assert "productive/dev1.png" in result
        assert "productive\\dev1.png" not in result

    def test_empty_manifest_returns_empty_dict(
        self, tmp_path: Path, loader: YamlManifestLoader
    ) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 1\nscreenshots: []\n", encoding="utf-8")
        assert loader.load(manifest) == {}

    def test_completely_empty_file(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("", encoding="utf-8")
        assert loader.load(manifest) == {}

    def test_extra_fields_ignored(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        # Дополнительные поля в manifest не должны ломать (forward compatibility)
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            """
version: 1
screenshots:
  - file: a.png
    employee_id: dev_1
    future_field_we_dont_know_yet: some_value
""",
            encoding="utf-8",
        )
        result = loader.load(manifest)
        assert result["a.png"].employee_id == "dev_1"


class TestYamlManifestLoaderErrors:
    def test_missing_file(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        with pytest.raises(ManifestParseError, match="not found"):
            loader.load(tmp_path / "missing.yaml")

    def test_invalid_yaml(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 1\nscreenshots: [\n  - file: a.png", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="invalid YAML"):
            loader.load(manifest)

    def test_root_not_mapping(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("- just a list\n", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="must be a mapping"):
            loader.load(manifest)

    def test_unsupported_version(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 99\nscreenshots: []\n", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="unsupported"):
            loader.load(manifest)

    def test_screenshots_not_list(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 1\nscreenshots: not_a_list\n", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="must be a list"):
            loader.load(manifest)

    def test_entry_not_mapping(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 1\nscreenshots:\n  - just_a_string\n", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="must be a mapping"):
            loader.load(manifest)

    def test_missing_file_field(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("version: 1\nscreenshots:\n  - employee_id: dev_1\n", encoding="utf-8")
        with pytest.raises(ManifestParseError, match="missing or empty 'file'"):
            loader.load(manifest)

    def test_invalid_metadata_field_value(self, tmp_path: Path, loader: YamlManifestLoader) -> None:
        # tracked_minutes отрицательный — отвергается ScreenshotMetadata
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "version: 1\nscreenshots:\n  - file: a.png\n    tracked_minutes: -1\n",
            encoding="utf-8",
        )
        with pytest.raises(ManifestParseError, match="invalid metadata"):
            loader.load(manifest)
