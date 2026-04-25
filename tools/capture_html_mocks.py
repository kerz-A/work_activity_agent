"""Уровень 2 синтеза: рендерит HTML mocks через Playwright в PNG.

Используется для PII-тестов и timeline static-серии.

Требования:
    uv run playwright install chromium

Запуск:
    uv run python tools/capture_html_mocks.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOCKS_DIR = PROJECT_ROOT / "mocks"
FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "screenshots"
MANIFEST_PATH = PROJECT_ROOT / "fixtures" / "manifest.yaml"

WIDTH = 1920
HEIGHT = 1080


class HtmlMock(NamedTuple):
    html_file: str
    output_subdir: str
    output_name: str
    employee_id: str
    project_id: str
    task_id: str
    tracked_task_title: str
    captured_at: datetime
    tracked_minutes: int
    app_hint: str
    repeats: int = 1


def _mocks() -> list[HtmlMock]:
    base_pii = datetime(2026, 4, 22, 16, 10, 0, tzinfo=UTC)
    return [
        HtmlMock(
            html_file="email_with_pii.html",
            output_subdir="sensitive",
            output_name="dev1_email_pii_001.png",
            employee_id="developer_1",
            project_id="client_crm",
            task_id="TASK-123",
            tracked_task_title="Fix payment retry bug",
            captured_at=base_pii,
            tracked_minutes=5,
            app_hint="Email client",
        ),
        HtmlMock(
            html_file="banking_test.html",
            output_subdir="sensitive",
            output_name="dev1_banking_test_001.png",
            employee_id="developer_1",
            project_id="client_crm",
            task_id="TASK-123",
            tracked_task_title="Fix payment retry bug",
            captured_at=base_pii + timedelta(minutes=5),
            tracked_minutes=5,
            app_hint="Online banking",
        ),
        HtmlMock(
            html_file="private_chat.html",
            output_subdir="sensitive",
            output_name="dev1_private_chat_001.png",
            employee_id="developer_1",
            project_id="client_crm",
            task_id="TASK-123",
            tracked_task_title="Fix payment retry bug",
            captured_at=base_pii + timedelta(minutes=10),
            tracked_minutes=5,
            app_hint="Test Messenger",
        ),
        HtmlMock(
            html_file="slack_chat.html",
            output_subdir="communication",
            output_name="dev1_slack_html_001.png",
            employee_id="developer_1",
            project_id="client_crm",
            task_id="TASK-123",
            tracked_task_title="Fix payment retry bug",
            captured_at=datetime(2026, 4, 22, 10, 15, 0, tzinfo=UTC),
            tracked_minutes=10,
            app_hint="Slack",
        ),
        HtmlMock(
            html_file="figma_static.html",
            output_subdir="timelines/static_figma",
            output_name="des1_static_html_{idx:03d}.png",
            employee_id="designer_1",
            project_id="cart_ui",
            task_id="TASK-50",
            tracked_task_title="Cart screen design",
            captured_at=datetime(2026, 4, 22, 14, 20, 0, tzinfo=UTC),
            tracked_minutes=5,
            app_hint="Figma",
            repeats=8,
        ),
    ]


def _capture(mock: HtmlMock, manifest_entries: list[dict[str, object]]) -> int:
    """Сделать screenshot HTML mock через Playwright. Возвращает кол-во созданных файлов."""
    from playwright.sync_api import sync_playwright

    html_path = MOCKS_DIR / mock.html_file
    if not html_path.exists():
        print(f"  SKIP: {html_path} not found")
        return 0

    out_dir = FIXTURES_DIR / mock.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    file_url = html_path.absolute().as_uri()
    count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
        page = context.new_page()
        page.goto(file_url)
        page.wait_for_load_state("networkidle")

        for i in range(mock.repeats):
            name = mock.output_name.format(idx=i + 1)
            out_path = out_dir / name
            page.screenshot(path=str(out_path), full_page=False)
            count += 1

            # captured_at смещаем на 5 минут для каждого повтора (имитация static)
            shifted = mock.captured_at + timedelta(minutes=5 * i)
            entry: dict[str, object] = {
                "file": f"{mock.output_subdir}/{name}",
                "employee_id": mock.employee_id,
                "project_id": mock.project_id,
                "task_id": mock.task_id,
                "tracked_task_title": mock.tracked_task_title,
                "captured_at": shifted.isoformat(),
                "tracked_minutes": mock.tracked_minutes,
                "app_hint": mock.app_hint,
            }
            manifest_entries.append(entry)

        browser.close()

    return count


def main() -> None:
    print(f"Capturing HTML mocks -> {FIXTURES_DIR}")
    new_entries: list[dict[str, object]] = []
    total = 0
    for mock in _mocks():
        count = _capture(mock, new_entries)
        print(f"  {mock.html_file} -> {count} file(s)")
        total += count

    # Дописать в manifest.yaml (preserving существующие записи)
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {"version": 1, "screenshots": []}

    existing_files = {entry["file"] for entry in existing.get("screenshots", [])}
    for entry in new_entries:
        if entry["file"] not in existing_files:
            existing["screenshots"].append(entry)

    existing["version"] = 1
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f, allow_unicode=True, sort_keys=False)

    print(f"Total: {total} files. Manifest updated: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
