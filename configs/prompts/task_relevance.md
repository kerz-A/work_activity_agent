---
name: task_relevance
version: 1.0.0
model_alias: text_primary
response_schema: work_activity_agent.domain.models.classification.RelevanceResult
description: Сравнение активности на скриншоте с tracked_task_title из manifest
---

Ты оцениваешь, соответствует ли активность на скриншоте заявленной рабочей задаче.

ВАЖНЫЕ ПРАВИЛА:
- Фиксируй ФАКТЫ, а не намерения.
- Если активность похожа на задачу — `high`.
- Если связь не очевидна, но и не противоречит — `medium`.
- Если активность явно не связана — `low` + соответствующий risk_flag.
- Если описание задачи слишком общее или неинформативное — `unclear`.
- Не пиши "сотрудник фармит время" / "сотрудник ищет работу".
  Пиши "обнаружены признаки активности, требующие проверки".

Маппинг активности → risk_flag (если relevance=low):
- сайт вакансий / резюме → `job_search_site`
- фриланс-биржа → `freelance_platform`
- развлечения, соцсети → `entertainment_content`
- личный мессенджер не по проекту → `personal_messenger`
- чужой репозиторий / другая CRM → `other_project_tool`
- сайт явно не по теме задачи → `unrelated_website`
- активность плохо связана с задачей в целом → `low_task_relevance`

Скриншот: {{ screenshot_id }}
Заявленная задача: "{{ tracked_task }}"
VisionResult:
```json
{{ vision_json }}
```

Ответь СТРОГО валидным JSON по схеме RelevanceResult:
- `screenshot_id`: "{{ screenshot_id }}"
- `tracked_task`: "{{ tracked_task }}"
- `screenshot_activity`: краткое описание (1 предложение) что видно на скрине
- `relevance`: high / medium / low / unclear
- `risk_flags`: tuple соответствующих RiskFlagType (пустой если relevance >= medium)
- `confidence`: 0.0-1.0
- `note`: пояснение если relevance=low (опц.)
