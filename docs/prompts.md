# Работа с промптами

Промпты — Markdown-файлы с YAML frontmatter в `configs/prompts/`. Загружаются `FilesystemPromptLoader`-ом, рендерятся jinja2 с переменными из узла, прокидываются в `LLMProvider.classify` / `vision_analyze` с `response_schema` для structured output.

## Содержание

1. [Каталог](#каталог)
2. [Структура файла](#структура-файла)
3. [Frontmatter поля](#frontmatter-поля)
4. [Жизненный цикл](#жизненный-цикл)
5. [Версионирование](#версионирование)
6. [Тестирование](#тестирование)
7. [Добавление нового промпта](#добавление-нового-промпта)

---

## Каталог

`configs/prompts/`:

| Файл | Используется в узле | response_schema |
|---|---|---|
| `vision_describe.md` | Vision | `VisionResult` |
| `classify_activity.md` | Classifier | `ClassificationResult` |
| `task_relevance.md` | Relevance | `RelevanceResult` |
| `report_summary.md` | Reports (опционально) | — (свободный текст) |
| `archive/` | — | старые версии после bump'а |

## Структура файла

```markdown
---
name: classify_activity
version: 1.1.0
model_alias: text_primary
response_schema: work_activity_agent.domain.models.classification.ClassificationResult
description: Классификация активности по 11 категориям из ТЗ §3
---

Ты классификатор активности. На вход получаешь VisionResult (оцифровку скриншота).
Твоя задача — отнести активность к ОДНОЙ из 11 категорий ТЗ §3.

## Правила
- ...

## Категории
- `productive_work` — IDE, Figma, Jira, GitHub, рабочий браузер
- ...

Активность из VisionResult:
{{ vision_json }}
```

После `---` идёт jinja2-шаблон. Переменные подставляются узлом через `template.render(...)`.

## Frontmatter поля

| Поле | Тип | Обязательно | Описание |
|---|---|:-:|---|
| `name` | str | ✅ | Логическое имя промпта. Должно совпадать с именем файла без расширения. |
| `version` | str (semver) | ✅ | Версия. Bump при семантическом изменении (см. ниже). |
| `model_alias` | str | ✅ | Алиас модели — `vision_primary` / `text_primary` / `embed_primary`. Резолвится в реальную модель через `configs/models.{profile}.yaml`. |
| `response_schema` | str (FQ class) | ⚠️ | Полное имя pydantic-класса для structured output. Если опущено — модель отвечает свободным текстом. |
| `description` | str | ⬜ | Короткое описание (1 строка) — для документации и `validate-prompts` команды. |

`response_schema` критичен: LiteLLM с Ollama использует его как `format=<schema>` для constrained decoding (модель физически не может выпустить токен, нарушающий схему). Для cloud — как `response_format={"type": "json_object"}` плюс инструкция в промпте.

## Жизненный цикл

```
configs/prompts/classify_activity.md
            │
            ▼
FilesystemPromptLoader.load("classify_activity")
            │
            ▼
PromptTemplate(name, version, model_alias, response_schema, jinja_template)
            │
            ▼
template.render(screenshot_id=..., vision_json=...)   ← jinja2-подстановка
            │
            ▼
deps.llm.classify(prompt=..., response_schema=ClassificationResult, model_alias="text_primary")
            │
            ▼
LiteLLMProvider:
  - alias → real model (configs/models.local.yaml: text_primary → ollama/gemma3:4b)
  - acompletion с format=schema (Ollama) или response_format=json_object (cloud)
  - retry + validation retry (см. infrastructure/llm/litellm_provider.py)
            │
            ▼
ClassificationResult.model_validate(json.loads(content))
```

`PromptTemplate.model_alias` идёт прямо в `LLMProvider`, без участия узла — узел не знает про конкретную модель.

## Версионирование

Используем семантическое версионирование (semver):

| Тип изменения | Bump | Пример |
|---|---|---|
| Орфография, форматирование, добавление пояснений без изменения семантики | patch (`1.0.0` → `1.0.1`) | Добавили пример к категории |
| Расширение правил, новые edge-cases, более детальные инструкции | minor (`1.0.0` → `1.1.0`) | Добавили категорию `needs_human_review` (фактический bump v1.1.0 в `classify_activity.md`) |
| Изменение `response_schema` или принципиальная смена логики | major (`1.1.0` → `2.0.0`) | Добавили обязательное поле в `ClassificationResult` |

При major-bump старая версия сохраняется в `configs/prompts/archive/<name>_v<old_version>.md` — это нужно для бэк-теста и сравнения.

## Тестирование

```bash
# Базовая валидация (frontmatter parses, schema FQ resolvable)
work-activity-agent validate-prompts
# или
uv run work-activity-agent validate-prompts
```

Эта команда:
1. Загружает каждый `.md` файл в `configs/prompts/` через `FilesystemPromptLoader`.
2. Парсит YAML frontmatter, проверяет обязательные поля.
3. Если указан `response_schema` — резолвит FQ путь и проверяет что класс импортируется.
4. Печатает `OK <name> v<version>` для каждого валидного, `FAIL <name>: <reason>` для битых.

Дополнительно — golden snapshot тесты в `tests/unit/infrastructure/prompts/test_filesystem_loader.py` фиксируют формат рендеринга.

## Добавление нового промпта

1. Создать `configs/prompts/<name>.md` с frontmatter.
2. Описать `response_schema` (если нужен structured output) — pydantic-модель в `domain/models/`.
3. Написать jinja2-шаблон, использовать переменные `{{ var }}` для подстановки из узла.
4. Запустить `work-activity-agent validate-prompts` — проверить что грузится.
5. Использовать в узле:
   ```python
   prompt_template = deps.prompt_loader.load("my_prompt")
   prompt = prompt_template.render(some_var=value)
   result = await deps.llm.classify(
       prompt=prompt,
       response_schema=MyResponseSchema,
       model_alias=prompt_template.model_alias,
   )
   ```
6. Покрыть unit-тестом + интеграционным тестом узла на FakeLLM.
