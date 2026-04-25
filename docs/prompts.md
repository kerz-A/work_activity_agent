# Работа с промптами

Полная версия документа появится на этапе 4 (создание первых промптов). Кратко:

- Промпты — `.md` файлы в `configs/prompts/` с YAML frontmatter (`name`, `version`, `model_alias`, `response_schema`)
- Загружаются через `FilesystemPromptLoader`, рендерятся jinja2
- Версионирование: bump семвера при изменении, старая версия → `configs/prompts/archive/`
- Тестирование: golden snapshot тесты + meta-тест дрейфа схемы
