# Формат `manifest.yaml`

`manifest.yaml` — единственный авторитетный источник метаданных скриншотов: кто, по какой задаче, когда. Файл должен лежать **рядом со скриншотами**, в корне input-директории (`<input>/manifest.yaml`).

Без manifest агент **попытается работать**, но:
- `employee_id=None` → все скрины попадут в группу `_unknown` → отчёты бесполезны
- `captured_at=None` → используется `mtime` файла на диске → Timeline-паттерны и дата отчёта будут неверными
- `tracked_task_title=None` → Relevance не сможет сравнить активность с задачей → все relevances будут `UNCLEAR`

**Поэтому manifest обязателен для проды.**

## Формат

```yaml
version: 1
screenshots:
  - file: <относительный_путь_к_PNG>
    employee_id: <строка>            # обязательно
    project_id: <строка>             # рекомендуется
    task_id: <строка>                # рекомендуется
    tracked_task_title: <строка>     # критично для Relevance
    captured_at: <ISO-8601 timestamp> # критично для Timeline
    tracked_minutes: <int>           # сколько минут трекер засчитал на эту задачу
    app_hint: <строка>               # подсказка для Vision (имя приложения)
```

### Поля

| Поле | Тип | Обязательно | Описание |
|---|---|:---:|---|
| `version` | int | ✅ | Версия формата. Сейчас `1` — единственная поддерживаемая. |
| `screenshots` | list | ✅ | Список записей. Каждая — один скрин. |
| `file` | str | ✅ | Путь к файлу относительно `input/`. Прямые слеши обязательны (Windows: `productive/dev1.png`, не `productive\dev1.png`). |
| `employee_id` | str | ⚠️ | ID сотрудника. Без него скрин попадает в группу `_unknown` и отчёт по нему практически бесполезен. |
| `project_id` | str | ⬜ | ID проекта. Используется в проектных отчётах. |
| `task_id` | str | ⬜ | ID задачи (например, `TASK-123`). Для трассировки. |
| `tracked_task_title` | str | ⚠️ | Название задачи в трекере. **Критично для Relevance** — без него агент не может сравнить активность с задачей. |
| `captured_at` | ISO-8601 | ⚠️ | Время захвата скрина с timezone (`2026-04-22T09:15:00+00:00`). **Критично для Timeline** — без него используется mtime файла. |
| `tracked_minutes` | int ≥ 0 | ⬜ | Сколько минут трекера соответствуют этому скрину. Используется в `tracked_time_drift` метрике риска. |
| `app_hint` | str | ⬜ | Подсказка Vision-узлу о том, что за приложение на скрине (например `"VS Code"`, `"Figma"`). Помогает классификатору. |

## Минимальный пример

```yaml
version: 1
screenshots:
  - file: shot_001.png
    employee_id: developer_1
    captured_at: '2026-04-22T09:00:00+00:00'
```

## Полный пример

```yaml
version: 1
screenshots:
  - file: productive/dev1_vscode_001.png
    employee_id: developer_1
    project_id: client_crm
    task_id: TASK-123
    tracked_task_title: "Fix payment retry bug"
    captured_at: '2026-04-22T09:00:00+00:00'
    tracked_minutes: 10
    app_hint: "VS Code"

  - file: communication/dev1_slack_001.png
    employee_id: developer_1
    project_id: client_crm
    task_id: TASK-123
    tracked_task_title: "Fix payment retry bug"
    captured_at: '2026-04-22T12:00:00+00:00'
    tracked_minutes: 5
    app_hint: "Slack"

  - file: timelines/static_figma/des1_static_001.png
    employee_id: designer_1
    project_id: cart_ui
    task_id: TASK-50
    tracked_task_title: "Cart screen design"
    captured_at: '2026-04-22T14:20:00+00:00'
    tracked_minutes: 5
    app_hint: "Figma"
```

## Конвенции

- Все timestamps — **в timezone-aware ISO-8601** (`+00:00` или `Z`). Без TZ агент откажется парсить.
- `file` — относительный путь от input-директории, прямые слеши.
- Если файл есть в input-директории, но отсутствует в manifest — он всё равно обработается, но с пустыми metadata.
- Если запись в manifest указывает на несуществующий файл — запись игнорируется (collector логирует warning).

## Fallback на имя файла

Если `captured_at` не указан в manifest, агент пытается выудить timestamp из имени файла по конвенции:

```
{employee}__{project}__{task}__{YYYY-MM-DDTHH-MM-SS}.png
```

Например: `dev1__crm__TASK-123__2026-04-22T09-00-00.png`. Сегменты `employee/project/task` не должны содержать `_`.

Если ни manifest.captured_at, ни конвенция не дают timestamp — берётся `mtime` файла на диске (это ненадёжно — на проде так делать не стоит).

## Проверка перед прогоном

Перед `work-activity-agent run` запустите:

```bash
work-activity-agent doctor
```

Команда проверит окружение и подскажет проблемы (нет Tesseract, нет Ollama, нет API ключей, etc.). Сам manifest проверяется в первом узле `collector`.
