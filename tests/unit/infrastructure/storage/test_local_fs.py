"""Тесты LocalFSStorage."""

from pathlib import Path

import pytest

from work_activity_agent.domain.errors import StorageError
from work_activity_agent.infrastructure.storage.local_fs import LocalFSStorage


@pytest.fixture
def storage() -> LocalFSStorage:
    return LocalFSStorage()


class TestListScreenshots:
    def test_lists_png(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        (tmp_path / "a.png").write_bytes(b"")
        (tmp_path / "b.PNG").write_bytes(b"")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.png").write_bytes(b"")
        result = list(storage.list_screenshots(tmp_path))
        assert len(result) == 3

    def test_lists_jpg_and_webp(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        for name in ("a.jpg", "b.jpeg", "c.webp"):
            (tmp_path / name).write_bytes(b"")
        result = list(storage.list_screenshots(tmp_path))
        assert len(result) == 3

    def test_excludes_non_images(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        (tmp_path / "doc.txt").write_bytes(b"")
        (tmp_path / "img.png").write_bytes(b"")
        result = list(storage.list_screenshots(tmp_path))
        assert len(result) == 1

    def test_missing_root_raises(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        with pytest.raises(StorageError, match="does not exist"):
            list(storage.list_screenshots(tmp_path / "missing"))

    def test_root_is_file_raises(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        f = tmp_path / "file.png"
        f.write_bytes(b"")
        with pytest.raises(StorageError, match="not a directory"):
            list(storage.list_screenshots(f))


class TestReadBytes:
    def test_reads_file(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        f = tmp_path / "a.png"
        f.write_bytes(b"hello")
        assert storage.read_bytes(f) == b"hello"

    def test_missing_raises(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        with pytest.raises(StorageError):
            storage.read_bytes(tmp_path / "missing.png")


class TestWriteRedacted:
    def test_writes_with_redacted_suffix(self, tmp_path: Path, storage: LocalFSStorage) -> None:
        original = tmp_path / "a.png"
        original.write_bytes(b"orig")
        out = storage.write_redacted(original, b"redacted")
        assert out == tmp_path / "a.redacted.png"
        assert out.read_bytes() == b"redacted"
