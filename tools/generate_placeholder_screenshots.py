"""Генератор placeholder PNG для CI-тестов (Уровень 1 синтеза).

Создаёт цветные PNG с текстом-описанием через Pillow.
Реальный Vision не запускается в CI — используется FakeLLMProvider с готовыми JSON.

Запуск:
    uv run python tools/generate_placeholder_screenshots.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import yaml
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1920
HEIGHT = 1080
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "screenshots"
MANIFEST_PATH = PROJECT_ROOT / "fixtures" / "manifest.yaml"


class Scenario(NamedTuple):
    """Описание одного placeholder-скрина."""

    category_dir: str
    file_name: str
    title: str
    subtitle: str
    bg_color: tuple[int, int, int]
    employee_id: str
    project_id: str
    task_id: str
    tracked_task_title: str
    captured_at: datetime
    tracked_minutes: int
    app_hint: str | None = None


# Палитра по категориям
COLORS = {
    "productive": (45, 55, 72),  # тёмно-синий (IDE)
    "communication": (74, 21, 75),  # фиолетовый (Slack)
    "research": (33, 41, 52),  # тёмный (StackOverflow)
    "admin": (250, 250, 250),  # светлый (Sheets)
    "neutral": (128, 128, 128),  # серый
    "non_work": (220, 38, 38),  # красный (YouTube)
    "job_search": (5, 102, 196),  # синий (LinkedIn)
    "other_project": (110, 80, 200),  # фиолетово-синий
    "static_figma": (240, 241, 243),  # светло-серый (Figma)
    "edge_cases": (20, 20, 20),  # очень тёмный
}


def _base_time() -> datetime:
    return datetime(2026, 4, 22, 9, 0, 0, tzinfo=UTC)


def _scenarios() -> list[Scenario]:
    """Полный набор placeholder-сценариев. ~50 штук."""
    base = _base_time()
    s: list[Scenario] = []

    # Productive (5)
    for i in range(5):
        s.append(
            Scenario(
                category_dir="productive",
                file_name=f"dev1_vscode_{i + 1:03d}.png",
                title="VS Code mock",
                subtitle=f"payment.service.ts — line {120 + i * 5}",
                bg_color=COLORS["productive"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(minutes=10 * i),
                tracked_minutes=10,
                app_hint="VS Code",
            )
        )

    # Productive — Figma (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="productive",
                file_name=f"des1_figma_{i + 1:03d}.png",
                title="Figma mock",
                subtitle=f"Cart screen — frame {i + 1}",
                bg_color=(240, 241, 243),
                employee_id="designer_1",
                project_id="cart_ui",
                task_id="TASK-50",
                tracked_task_title="Cart screen design",
                captured_at=base + timedelta(hours=1, minutes=15 * i),
                tracked_minutes=15,
                app_hint="Figma",
            )
        )

    # Productive — GitHub PR (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="productive",
                file_name=f"dev1_github_pr_{i + 1:03d}.png",
                title="GitHub PR mock",
                subtitle=f"Pull request #{42 + i} — auth fix",
                bg_color=(255, 255, 255),
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=2, minutes=10 * i),
                tracked_minutes=10,
                app_hint="GitHub",
            )
        )

    # Communication — Slack (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="communication",
                file_name=f"dev1_slack_{i + 1:03d}.png",
                title="Slack mock",
                subtitle=f"#client-crm — message {i + 1}",
                bg_color=COLORS["communication"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=3, minutes=5 * i),
                tracked_minutes=5,
                app_hint="Slack",
            )
        )

    # Research — StackOverflow / MDN (3)
    for i, site in enumerate(["StackOverflow", "MDN", "Python docs"]):
        s.append(
            Scenario(
                category_dir="research",
                file_name=f"dev1_research_{i + 1:03d}.png",
                title=f"{site} mock",
                subtitle="Reading: how to handle async retry",
                bg_color=COLORS["research"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=3, minutes=20 + 10 * i),
                tracked_minutes=10,
                app_hint=site,
            )
        )

    # Admin work (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="admin",
                file_name=f"pm1_admin_{i + 1:03d}.png",
                title="Google Sheets mock",
                subtitle="Sprint planning Q2 2026",
                bg_color=COLORS["admin"],
                employee_id="pm_1",
                project_id="client_crm",
                task_id="TASK-200",
                tracked_task_title="Sprint planning",
                captured_at=base + timedelta(hours=4, minutes=10 * i),
                tracked_minutes=10,
                app_hint="Google Sheets",
            )
        )

    # Neutral / unclear (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="neutral",
                file_name=f"dev1_neutral_{i + 1:03d}.png",
                title="Desktop mock",
                subtitle="Window switcher / app drawer",
                bg_color=COLORS["neutral"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=4, minutes=30 + 5 * i),
                tracked_minutes=5,
                app_hint=None,
            )
        )

    # Non-work — YouTube/Reddit (3)
    for i, site in enumerate(["YouTube", "Reddit", "News site"]):
        s.append(
            Scenario(
                category_dir="non_work",
                file_name=f"dev1_nonwork_{i + 1:03d}.png",
                title=f"{site} mock",
                subtitle="Entertainment content",
                bg_color=COLORS["non_work"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=5, minutes=10 * i),
                tracked_minutes=10,
                app_hint=site,
            )
        )

    # Job search (3)
    for i, site in enumerate(["hh.ru", "LinkedIn jobs", "Indeed"]):
        s.append(
            Scenario(
                category_dir="job_search",
                file_name=f"dev1_jobsearch_{i + 1:03d}.png",
                title=f"{site} mock",
                subtitle="Vacancy: Senior Python Developer",
                bg_color=COLORS["job_search"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=5, minutes=30 + 10 * i),
                tracked_minutes=10,
                app_hint=site,
            )
        )

    # Other project (3)
    for i in range(3):
        s.append(
            Scenario(
                category_dir="other_project",
                file_name=f"dev1_otherproject_{i + 1:03d}.png",
                title="Other project mock",
                subtitle=f"Repo: someone-else/{['side-project','consulting','hobby-app'][i]}",
                bg_color=COLORS["other_project"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=6, minutes=10 * i),
                tracked_minutes=10,
                app_hint=None,
            )
        )

    # Edge cases (3)
    for i, label in enumerate(["dark theme", "small font", "russian UI"]):
        s.append(
            Scenario(
                category_dir="edge_cases",
                file_name=f"edge_{i + 1:03d}.png",
                title=f"Edge case: {label}",
                subtitle="Robustness test",
                bg_color=COLORS["edge_cases"],
                employee_id="developer_1",
                project_id="client_crm",
                task_id="TASK-123",
                tracked_task_title="Fix payment retry bug",
                captured_at=base + timedelta(hours=6, minutes=30 + 5 * i),
                tracked_minutes=5,
                app_hint=None,
            )
        )

    # Timeline series — static_figma: 8 одинаковых
    for i in range(8):
        s.append(
            Scenario(
                category_dir="timelines/static_figma",
                file_name=f"des1_static_{i + 1:03d}.png",
                title="Figma static",
                subtitle="Cart screen — UNCHANGED",
                bg_color=COLORS["static_figma"],
                employee_id="designer_1",
                project_id="cart_ui",
                task_id="TASK-50",
                tracked_task_title="Cart screen design",
                captured_at=datetime(2026, 4, 22, 14, 20, 0, tzinfo=UTC) + timedelta(minutes=5 * i),
                tracked_minutes=5,
                app_hint="Figma",
            )
        )

    # Timeline series — work → break → jobsearch (8)
    transition_base = datetime(2026, 4, 22, 15, 0, 0, tzinfo=UTC)
    transitions = [
        ("productive", "VS Code work", "VS Code"),
        ("productive", "VS Code work", "VS Code"),
        ("productive", "VS Code work", "VS Code"),
        ("non_work", "YouTube break", "YouTube"),
        ("non_work", "YouTube break", "YouTube"),
        ("job_search", "hh.ru job search", "hh.ru"),
        ("job_search", "LinkedIn vacancies", "LinkedIn"),
        ("job_search", "hh.ru job search", "hh.ru"),
    ]
    for i, (subcat, label, app) in enumerate(transitions):
        s.append(
            Scenario(
                category_dir="timelines/work_to_jobsearch",
                file_name=f"dev2_transition_{i + 1:03d}.png",
                title=f"Transition #{i + 1}: {label}",
                subtitle="Timeline pattern test",
                bg_color=COLORS.get(subcat, COLORS["productive"]),
                employee_id="developer_2",
                project_id="client_crm",
                task_id="TASK-150",
                tracked_task_title="Implement OAuth callback",
                captured_at=transition_base + timedelta(minutes=10 * i),
                tracked_minutes=10,
                app_hint=app,
            )
        )

    # Timeline — productive day (5)
    productive_day_base = datetime(2026, 4, 23, 9, 0, 0, tzinfo=UTC)
    for i, (subcat, label, app) in enumerate(
        [
            ("productive", "VS Code morning", "VS Code"),
            ("research", "StackOverflow help", "StackOverflow"),
            ("communication", "Slack project chat", "Slack"),
            ("productive", "GitHub PR review", "GitHub"),
            ("productive", "VS Code afternoon", "VS Code"),
        ]
    ):
        s.append(
            Scenario(
                category_dir="timelines/productive_day",
                file_name=f"dev3_productive_{i + 1:03d}.png",
                title=f"Productive #{i + 1}: {label}",
                subtitle="Healthy work pattern",
                bg_color=COLORS.get(subcat, COLORS["productive"]),
                employee_id="developer_3",
                project_id="client_crm",
                task_id="TASK-180",
                tracked_task_title="Refactor user service",
                captured_at=productive_day_base + timedelta(hours=i),
                tracked_minutes=60,
                app_hint=app,
            )
        )

    return s


def _draw_placeholder(scenario: Scenario, output_path: Path) -> None:
    """Нарисовать одиночный placeholder PNG."""
    img = Image.new("RGB", (WIDTH, HEIGHT), color=scenario.bg_color)
    draw = ImageDraw.Draw(img)

    text_color = _contrasting_text_color(scenario.bg_color)

    try:
        title_font = ImageFont.truetype("arial.ttf", 80)
        subtitle_font = ImageFont.truetype("arial.ttf", 48)
        meta_font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        meta_font = ImageFont.load_default()

    draw.text((100, 200), scenario.title, fill=text_color, font=title_font)
    draw.text((100, 350), scenario.subtitle, fill=text_color, font=subtitle_font)

    # Метаданные внизу
    meta_lines = [
        f"employee_id: {scenario.employee_id}",
        f"project_id: {scenario.project_id}",
        f"task_id: {scenario.task_id}",
        f"task: {scenario.tracked_task_title}",
        f"captured_at: {scenario.captured_at.isoformat()}",
        f"app_hint: {scenario.app_hint or '-'}",
    ]
    y = HEIGHT - 280
    for line in meta_lines:
        draw.text((100, y), line, fill=text_color, font=meta_font)
        y += 40

    # Маркер: Pillow placeholder, не настоящий скрин
    draw.text(
        (WIDTH - 600, HEIGHT - 60),
        "[PLACEHOLDER — NOT A REAL SCREENSHOT]",
        fill=text_color,
        font=meta_font,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", optimize=True)


def _contrasting_text_color(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Чёрный или белый текст в зависимости от яркости фона (W3C luminance)."""
    luminance = (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) / 255
    return (0, 0, 0) if luminance > 0.5 else (240, 240, 240)


def _build_manifest(scenarios: list[Scenario]) -> dict[str, object]:
    """Собрать содержимое manifest.yaml."""
    entries = []
    for s in scenarios:
        rel_path = f"{s.category_dir}/{s.file_name}"
        entry: dict[str, object] = {
            "file": rel_path,
            "employee_id": s.employee_id,
            "project_id": s.project_id,
            "task_id": s.task_id,
            "tracked_task_title": s.tracked_task_title,
            "captured_at": s.captured_at.isoformat(),
            "tracked_minutes": s.tracked_minutes,
        }
        if s.app_hint:
            entry["app_hint"] = s.app_hint
        entries.append(entry)
    return {"version": 1, "screenshots": entries}


def main() -> None:
    scenarios = _scenarios()
    print(f"Generating {len(scenarios)} placeholder screenshots -> {FIXTURES_DIR}")

    for s in scenarios:
        out = FIXTURES_DIR / s.category_dir / s.file_name
        _draw_placeholder(s, out)
    print(f"Done. {len(scenarios)} files written.")

    manifest_data = _build_manifest(scenarios)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest_data, f, allow_unicode=True, sort_keys=False)
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
