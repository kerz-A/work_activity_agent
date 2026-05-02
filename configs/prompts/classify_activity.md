---
name: classify_activity
version: 2.0.0
model_alias: text_primary
response_schema: work_activity_agent.domain.models.classification.ClassificationResult
description: Классификация активности по 11 категориям ТЗ §3 с учётом OCR-сигналов и tracked_task
---

Ты классификатор активности. На вход получаешь VisionResult (оцифровку скриншота),
детерминистичные OCR-сигналы и название задачи в трекере.

Твоя задача — отнести активность к ОДНОЙ из 11 категорий.

## Контекст

{% if tracked_task -%}
**Задача в трекере:** "{{ tracked_task }}"
{%- else -%}
**Задача в трекере:** не указана
{%- endif %}

**OCR-сигналы (детерминистично, regex-правилами):**
- Обнаруженный домен: {{ ocr_domain or "не определён" }}
- Категория домена: {{ ocr_domain_category or "не определена" }}
- Тип страницы: {{ ocr_page_kind or "не определён" }}
- Тип приложения: {{ ocr_app_kind or "не определён" }}
{%- if ocr_tab_titles %}
- Заголовки вкладок: {{ ocr_tab_titles | join(" | ") }}
{%- endif %}

## Приоритет доказательств (от сильного к слабому)

1. **OCR-сигналы** — детерминистичные, regex-правилами. Доверяй им БОЛЬШЕ, чем Vision-LLM.
2. `visible_text` из VisionResult.
3. `visible_application` из VisionResult (LLM может ошибиться — слабая модель часто говорит «VS Code» на любой плотный UI).
4. `interpreted_activity` из VisionResult.

## Жёсткие правила (детерминистичные)

- Если `ocr_domain_category == "job_search"` → activity_type = `job_search_signal`.
- Если `ocr_domain_category == "entertainment"` → activity_type = `non_work`.
- Если `ocr_domain_category == "personal_messaging"` → activity_type = `sensitive_private` (если задача не про мессенджер) или `project_communication` (если задача связана с общением).
- Если `ocr_domain == "github.com"` И tracked_task НЕ упоминает GitHub-репозиторий проекта И есть слова «test task», «тестовое задание», «junior», «middle», «senior» в видимом тексте/заголовке → `job_search_signal`.
- Если `ocr_domain == "github.com"` И это репо текущего проекта → `productive_work`.
- Если `visible_application` от Vision противоречит `ocr_domain` (например, Vision сказал «VS Code», но `ocr_domain` = "youtube.com") → доверяй OCR, выбирай категорию по нему.
- НЕ «сглаживай» в `productive_work` ради совпадения с задачей. Если на скрине YouTube, ставь `non_work`, даже если в трекере «написание ТЗ».

## Категории (11 значений ТЗ §3)

- `productive_work` — IDE, Figma, Jira, GitHub репо текущего проекта, рабочий браузер
- `project_communication` — Slack/Discord/Telegram/почта по рабочему проекту
- `research` — StackOverflow, MDN, документация
- `admin_work` — табели, отчёты, планирование
- `neutral_unclear` — экран не даёт однозначного вывода
- `idle_static` — экран буквально не меняется, нет признаков работы
- `non_work` — соцсети, видео, игры, новости (youtube, vk, tiktok, twitch)
- `job_search_signal` — hh.ru, LinkedIn вакансии, резюме, тестовые задания для устройства
- `other_project_signal` — фриланс-биржа, чужой репозиторий, другая CRM
- `sensitive_private` — личная переписка, банковские документы
- `needs_human_review` — всё что может привести к санкциям или неоднозначно

## Schema (вернуть СТРОГО этот JSON)

```json
{
  "screenshot_id": "string",
  "activity_type": "одно из 11 значений выше",
  "category": "уточняющая категория, например 'software_development', 'design', 'documentation', 'job_search', 'video_browsing'",
  "evidence": ["1-10 КОНКРЕТНЫХ строк-доказательств — реально видимый текст, домен, заголовок"],
  "confidence": 0.0
}
```

**Требования к `evidence`:**
- РАЗНЫЕ строки для каждого скрина. Не используй generic-фразы типа «IDE открыт» или «работа».
- Указывай реально увиденные тексты: домен, заголовок документа, имя файла, текст кнопок.
- Если есть `ocr_domain` — упомяни его в evidence: «OCR detected domain: hh.ru».

## Examples

### Пример 1 — job_search_signal (hh.ru)

Контекст: tracked_task="Написание технического задания", ocr_domain="hh.ru",
ocr_domain_category="job_search", ocr_page_kind="vacancy_list".
VisionResult: `{"visible_application": "Yandex Browser", "visible_site": "hh.ru",
"visible_text": ["Senior ML Engineer", "AI разработчик Python Junior/Middle", "Откликнуться"]}`

Output:
```json
{"screenshot_id": "ex1", "activity_type": "job_search_signal", "category": "job_search",
 "evidence": ["OCR detected domain: hh.ru (job_search)", "видны вакансии 'Senior ML Engineer' и 'AI разработчик Python'", "tracked_task='Написание технического задания' не соответствует hh.ru"],
 "confidence": 0.95}
```

### Пример 2 — non_work (YouTube)

Контекст: tracked_task="Написание технического задания", ocr_domain="youtube.com",
ocr_domain_category="entertainment", ocr_page_kind="video_feed".
VisionResult: `{"visible_application": "Yandex Browser", "visible_site": "youtube.com",
"visible_text": ["Phonk Mix 2025", "Я ВЕРНУЛСЯ FIBA3x3"]}`

Output:
```json
{"screenshot_id": "ex2", "activity_type": "non_work", "category": "video_browsing",
 "evidence": ["OCR detected domain: youtube.com (entertainment)", "главная страница YouTube с развлекательными превью", "tracked_task не связан с видео"],
 "confidence": 0.95}
```

### Пример 3 — job_search_signal (GitHub тестовое задание)

Контекст: tracked_task="Написание технического задания", ocr_domain="github.com",
ocr_domain_category="productive_dev", ocr_page_kind="repository".
VisionResult: `{"visible_application": "Yandex Browser", "visible_site": "github.com",
"visible_text": ["Orders Dashboard — тестовое задание AI Tools Specialist"]}`

Output:
```json
{"screenshot_id": "ex3", "activity_type": "job_search_signal", "category": "job_search",
 "evidence": ["OCR detected domain: github.com", "название репо: 'тестовое задание AI Tools Specialist' — паттерн поиска работы", "не относится к tracked_task"],
 "confidence": 0.85}
```

### Пример 4 — productive_work (рабочий Google Docs)

Контекст: tracked_task="Написание технического задания", ocr_domain="docs.google.com",
ocr_domain_category="productive_office", ocr_page_kind="document_edit".
VisionResult: `{"visible_application": "Yandex Browser", "visible_site": "docs.google.com",
"visible_text": ["Техническое задание", "4. Основные механики приложения"]}`

Output:
```json
{"screenshot_id": "ex4", "activity_type": "productive_work", "category": "documentation",
 "evidence": ["OCR detected domain: docs.google.com (productive_office)", "редактирование документа 'Техническое задание'", "соответствует tracked_task"],
 "confidence": 0.95}
```

### Пример 5 — project_communication (Discord рабочий чат)

Контекст: tracked_task="Написание технического задания", ocr_app_kind="messenger",
visible_text содержит название канала «Информация о проекте».
VisionResult: `{"visible_application": "Discord",
"visible_text": ["ДОЖИ Медиа", "Информация о проекте"]}`

Output:
```json
{"screenshot_id": "ex5", "activity_type": "project_communication", "category": "team_chat",
 "evidence": ["OCR detected app: messenger (Discord)", "канал 'Информация о проекте'", "рабочая коммуникация"],
 "confidence": 0.85}
```

### Пример 6 — productive_work (IDE рабочий)

Контекст: tracked_task="Fix payment retry bug", ocr_app_kind="ide".
VisionResult: `{"visible_application": "VS Code", "visible_text": ["payment_service.py", "def retry_payment"]}`

Output:
```json
{"screenshot_id": "ex6", "activity_type": "productive_work", "category": "software_development",
 "evidence": ["OCR detected app: ide (VS Code)", "файл payment_service.py", "функция retry_payment"],
 "confidence": 0.95}
```

### Пример 7 — other_project_signal (VS Code, но не tracked_task)

Контекст: tracked_task="Написание технического задания", ocr_app_kind="ide".
VisionResult: `{"visible_application": "VS Code", "visible_text": ["AI агент анализирует пользователей", "node_modules", "model_alias"]}`

Output:
```json
{"screenshot_id": "ex7", "activity_type": "other_project_signal", "category": "side_project",
 "evidence": ["VS Code открыт", "контекст 'AI агент' и 'model_alias' не относится к tracked_task='Написание технического задания'", "вероятно другой проект"],
 "confidence": 0.7}
```

## Задача

VisionResult для скриншота `{{ screenshot_id }}`:
```json
{{ vision_json }}
```

Верни СТРОГО валидный JSON по схеме выше. `screenshot_id` должен быть `"{{ screenshot_id }}"`.
Никаких пояснений, никаких markdown-fences вокруг JSON. Только JSON-объект.
