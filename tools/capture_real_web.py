"""Уровень 3 синтеза: рендерит публичные web-страницы через Playwright.

Используется для live_llm тестов (по требованию вручную).
Не запускается в CI — это медленно и может быть нестабильно.

Требования:
    uv run playwright install chromium

Запуск:
    uv run python tools/capture_real_web.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "fixtures" / "screenshots" / "real_web"

WIDTH = 1920
HEIGHT = 1080


class WebScenario(NamedTuple):
    category: str
    name: str
    url: str
    employee_id: str
    captured_at: datetime
    tracked_task_title: str


SCENARIOS: list[WebScenario] = [
    WebScenario(
        category="research",
        name="stackoverflow_python",
        url="https://stackoverflow.com/questions/3437059/does-python-have-a-string-contains-substring-method",
        employee_id="developer_1",
        captured_at=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        tracked_task_title="Fix payment retry bug",
    ),
    WebScenario(
        category="research",
        name="mdn_fetch",
        url="https://developer.mozilla.org/en-US/docs/Web/API/fetch",
        employee_id="developer_1",
        captured_at=datetime(2026, 4, 22, 10, 10, tzinfo=UTC),
        tracked_task_title="Fix payment retry bug",
    ),
    WebScenario(
        category="productive",
        name="github_anthropic_repo",
        url="https://github.com/anthropics/anthropic-sdk-python",
        employee_id="developer_1",
        captured_at=datetime(2026, 4, 22, 10, 20, tzinfo=UTC),
        tracked_task_title="Fix payment retry bug",
    ),
    WebScenario(
        category="non_work",
        name="reddit_aww",
        url="https://www.reddit.com/r/aww/",
        employee_id="developer_1",
        captured_at=datetime(2026, 4, 22, 11, 30, tzinfo=UTC),
        tracked_task_title="Fix payment retry bug",
    ),
    WebScenario(
        category="job_search",
        name="hh_python_dev",
        url="https://hh.ru/search/vacancy?text=python+developer",
        employee_id="developer_1",
        captured_at=datetime(2026, 4, 22, 16, 10, tzinfo=UTC),
        tracked_task_title="Fix payment retry bug",
    ),
]


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing {len(SCENARIOS)} real web pages -> {OUTPUT_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
        )

        for scenario in SCENARIOS:
            try:
                page = context.new_page()
                page.goto(scenario.url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                out_path = OUTPUT_DIR / f"{scenario.category}__{scenario.name}.png"
                page.screenshot(path=str(out_path), full_page=False)
                print(f"  OK {scenario.name}")
                page.close()
            except Exception as e:
                print(f"  FAIL {scenario.name}: {type(e).__name__}: {e}")

        browser.close()

    print("Done.")
    print("NOTE: Real web screenshots not added to manifest.yaml automatically.")
    print("      Add manually if needed for live_llm tests.")


if __name__ == "__main__":
    main()
