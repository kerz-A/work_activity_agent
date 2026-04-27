# Examples

## `sample_input/`
Минимальный пример входной директории — один `manifest.yaml` с тремя записями. Положите рядом ваши PNG (`shot_001.png`, `shot_002.png`, `shot_003.png`) и запустите агента:

```bash
work-activity-agent run --input ./examples/sample_input --output ./out
```

## `sample_output/`
Реальные отчёты, сгенерированные агентом на полном наборе fixtures (5 сотрудников × 68 скринов):

- `employee_developer_1.md` / `.json` — дневной отчёт по разработчику с risk-флагами (job_search_signal детектен)
- `project_client_crm.md` — проектный отчёт с productive_ratio и топ-инструментами
- `screenshots_table.md` — сводная таблица всех скринов (§15 ТЗ)

Это пример того, что вы получите на выходе на ваших данных.
